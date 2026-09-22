"""Dataset for Swift trained on gridded *observations* rather than ERA5.

The fields here are sparse: roughly 11% of cells carry a surface observation in
any 6-hour window, and ~1% per pressure level for radiosondes. Swift's variables
are its input as well as its target, so a sparse field is the state the model
must roll forward -- which is the hard part of training on observations at all.

The approach follows AIFS-DOP (arXiv:2606.19093) and every other published
observation-trained forecaster: **the input is densified, the loss is masked**.
Unobserved cells are imputed with the climatological mean, which is exactly zero
after standardization, and the loss is weighted by how often each cell is
actually observed (see `observation_weight`). The masked loss is what allows the
network to emit -- and therefore autoregress -- a complete field.

Two hazards this class exists to avoid, both silent:

1. `ERA5Dataset._load_file` runs `_fill_nan`, which replaces NaN with the
   field's `nanmin`. On an 11%-filled grid that fills 89% of the world with the
   coldest observed value. `_load_file` is overridden here; do not remove the
   override.
2. `trainer.py` runs `torch.nan_to_num(param.grad, nan=0)`. A single NaN
   reaching the loss NaNs every gradient, and those are then zeroed -- training
   completes, logs a NaN loss, and updates nothing. Nothing may leave this class
   non-finite; `__getitem__` asserts it.

The grids are produced by `work/nnja/nnja_grid_pilot.py` and split into
train/val/test by `work/nnja/make_splits.py`; statistics come from
`work/nnja/make_norm_stats.py`.
"""

import os
from datetime import datetime, timedelta, timezone
from glob import glob
from typing import Tuple

import h5py
import numpy as np
import torch

from swift.data.era5 import ERA5Dataset

# The grids are built per instrument group; a variable lives in exactly one.
SOURCES = ["adpsfc", "adpupa"]

STEP_HOURS = 6


def _parse_window(name: str) -> datetime:
    """'20100615_12.h5' -> datetime(2010, 6, 15, 12, tzinfo=utc)."""
    stem = os.path.basename(name).split(".")[0]
    return datetime.strptime(stem, "%Y%m%d_%H").replace(tzinfo=timezone.utc)


class ERA5ObsDataset(ERA5Dataset):
    """Sparse observation grids, densified on read, with an observation mask.

    Named `ERA5Obs*` deliberately: `train.py` gates online rollout validation on
    the substring "era5" appearing in the dataset's `_target_`.
    """

    def __init__(
        self,
        root: str,
        variables: list[str],
        forcings: list[str] = [],
        intervals: list[int] = [6],
        split: str = "train",
        residual: bool = False,
        min_count: int = 1,
        weight_floor: float = 0.02,
    ):
        # NOTE: deliberately does not call super().__init__ -- that globs a flat
        # <root>/<split>/*.h5, and our windows are split across two source dirs.
        torch.utils.data.Dataset.__init__(self)
        assert sorted(intervals) in ([6], [12], [24], [6, 12], [6, 24], [12, 24],
                                     [6, 12, 24]), "must be combination of [6, 12, 24]"

        self.root = root
        self.split = split
        self.variables = variables
        self.forcings = forcings
        self.intervals = intervals
        self.residual = residual
        self.min_count = min_count
        self.weight_floor = weight_floor

        self._resolve_sources()
        self._build_index()

        self.x_means, self.x_stds, self.t_means, self.t_stds = self._setup_standardize()
        self._shape = (len(variables), *self._grid)

    # -- construction ----------------------------------------------------

    def _resolve_sources(self):
        """Work out which source directory provides each requested variable."""
        available = {}
        self._grid = None
        for s in SOURCES:
            fs = sorted(glob(os.path.join(self.root, self.split, s, "*.h5")))
            if not fs:
                continue
            with h5py.File(fs[0]) as f:
                for k in f["input"]:
                    if k == "time" or k.endswith(("__cnt", "__min", "__max")):
                        continue
                    available.setdefault(k, s)
                    if self._grid is None:
                        # take the grid from a key in THIS file -- `available`
                        # spans sources, so its first key may live elsewhere
                        self._grid = f["input"][k][()].shape

        missing = [v for v in self.variables + self.forcings if v not in available]
        if missing:
            raise ValueError(
                f"variables not present in any source under "
                f"{self.root}/{self.split}: {missing}"
            )
        self.var_source = {v: available[v] for v in self.variables + self.forcings}

    def _build_index(self):
        """Index windows on a strict 6-hourly timeline.

        `InfiniteSampler` builds `np.arange(len(dataset))` and `__getitem__`
        reaches `idx + offset*delta//6`, so position must mean time. Windows
        absent from the archive (real gaps exist) leave a hole in `self.files`,
        and `self._starts` lists only the positions whose whole forward span is
        present -- the dense index the sampler sees maps through it.
        """
        names = set()
        for s in SOURCES:
            for p in glob(os.path.join(self.root, self.split, s, "*.h5")):
                names.add(os.path.basename(p))
        if not names:
            raise ValueError(f"no windows under {self.root}/{self.split}")

        times = sorted(_parse_window(n) for n in names)
        t0, t1 = times[0], times[-1]
        n = int((t1 - t0).total_seconds() // 3600 // STEP_HOURS) + 1

        self.times = [t0 + timedelta(hours=STEP_HOURS * i) for i in range(n)]
        self.files = []
        for t in self.times:
            w = f"{t:%Y%m%d_%H}.h5"
            entry = {}
            for s in SOURCES:
                p = os.path.join(self.root, self.split, s, w)
                if os.path.exists(p):
                    entry[s] = p
            self.files.append(entry or None)

        # A start is usable only if every frame it will reach exists. The
        # trainer may ask for offset>1 during multistep finetuning, so reserve
        # room for two hops of the longest interval.
        reach = 2 * (max(self.intervals) // STEP_HOURS)
        self._starts = np.array(
            [i for i in range(len(self.files) - reach)
             if self.files[i] is not None
             and all(self.files[i + k] is not None for k in range(1, reach + 1))],
            dtype=np.int64,
        )
        if self._starts.size == 0:
            raise ValueError(
                f"no usable start positions in split '{self.split}' "
                f"({len(names)} windows, {sum(f is None for f in self.files)} gaps)"
            )

    # -- reading ---------------------------------------------------------

    def _load_file(self, path, variables: list[str]) -> np.ndarray:
        """Not used -- see `_load_window`.

        Overridden to guarantee `ERA5Dataset._load_file` (and its `_fill_nan`,
        which would fill unobserved cells with the field minimum) can never run
        against sparse data.
        """
        raise NotImplementedError(
            "ERA5ObsDataset reads through _load_window; _load_file is disabled "
            "because ERA5Dataset._fill_nan would corrupt sparse fields."
        )

    def _load_window(self, pos: int, variables: list[str]) -> Tuple[np.ndarray, np.ndarray]:
        """Read one analysis window.

        Returns `(values, mask)` in **raw units**, with unobserved cells set to
        NaN. Imputation happens after standardization so that a filled cell is
        exactly the climatological mean.
        """
        entry = self.files[pos]
        if entry is None:
            raise IndexError(f"window {pos} ({self.times[pos]}) is absent")

        out = np.empty((len(variables), *self._grid), dtype=np.float32)
        mask = np.zeros_like(out, dtype=bool)
        handles = {s: h5py.File(p, "r") for s, p in entry.items()}
        try:
            for i, v in enumerate(variables):
                src = self.var_source[v]
                g = handles[src]["input"]
                a = g[v][()].astype(np.float32)
                ok = np.isfinite(a)
                if v + "__cnt" in g:
                    ok &= g[v + "__cnt"][()] >= self.min_count
                out[i] = np.where(ok, a, np.nan)
                mask[i] = ok
        finally:
            for h in handles.values():
                h.close()
        return out, mask

    def _standardize_and_impute(self, raw: np.ndarray, mask: np.ndarray) -> np.ndarray:
        """Standardize observed cells; set unobserved ones to zero (= the mean)."""
        m = self.x_means[: raw.shape[0]]
        s = self.x_stds[: raw.shape[0]]
        z = (np.where(mask, raw, 0.0) - m) / s
        return np.where(mask, z, 0.0).astype(np.float32)

    # -- the mask the loss uses ------------------------------------------

    def observation_weight(self) -> torch.Tensor:
        """Per-variable climatological observation frequency, `[1, C, H, W]`.

        Multiplied into the loss alongside the existing latitude and variable
        weights, this restricts the gradient to where observations actually are.
        A climatological weight is used rather than a per-sample mask because
        the observing network is close to fixed -- the 6-hour mask IoU is 0.902,
        and 84% of surface observations fall in the 9.6% of cells observed in
        >=90% of windows -- and because it needs no change to the batch tuple or
        to any loss signature.

        It must be per-variable: the joint stable network across all 69
        variables is 0.22% of the grid against ~1.5% per variable, so one shared
        mask would collapse the trainable area.
        """
        p = os.path.join(self.root, "obs_freq.npz")
        if not os.path.exists(p):
            raise FileNotFoundError(
                f"{p} not found -- run work/nnja/make_norm_stats.py first"
            )
        with np.load(p) as d:
            w = np.stack([d[v] for v in self.variables], axis=0).astype(np.float32)
        # A hard zero on never-observed cells means the model gets no gradient
        # at all across ~87% of the grid -- yet it must emit values there, and in
        # residual autoregression those values feed straight back in as the next
        # input. A small floor buys spatial coherence off-network: at 0.02 about
        # 14% of the loss mass lands on unobserved cells. Set 0.0 to ablate.
        w = np.maximum(w, self.weight_floor)
        t = torch.from_numpy(w)[None]                 # [1, C, H, W]
        # Normalize to mean 1 over observed area so the loss scale is comparable
        # to the dense-ERA5 case and the configured learning rate still applies.
        denom = t.mean().clamp_min(1e-8)
        return t / denom

    # -- dataset protocol -------------------------------------------------

    def __len__(self) -> int:
        return int(self._starts.size)

    def get_time(self, idx: int) -> np.datetime64:
        return np.datetime64(self.times[self._starts[int(idx)]].replace(tzinfo=None), "s")

    def get_forcings(self, idx: int) -> torch.Tensor:
        if not self.forcings:
            return torch.empty(0, *self._grid)
        pos = self._starts[int(idx) % len(self)]
        raw, mask = self._load_window(pos, self.forcings)
        m = self.x_means[len(self.variables):]
        s = self.x_stds[len(self.variables):]
        z = np.where(mask, (np.where(mask, raw, 0.0) - m) / s, 0.0)
        return torch.from_numpy(z.astype(np.float32))

    def __getitem__(self, spec):
        if isinstance(spec, tuple):
            spec = tuple(int(i) for i in spec)
        else:
            spec = int(spec)

        match spec:
            case int() as idx:
                offset, delta = 1, None
            case (int() as idx, int() as off):
                offset, delta = off, None
            case (int() as idx, int() as off, int() as d):
                offset, delta = off, d
            case _:
                raise ValueError(f"Invalid index spec: {spec!r}")

        if delta is None:
            delta = int(np.random.choice(self.intervals))

        pos = int(self._starts[idx])
        step = offset * delta // STEP_HOURS

        xr, xm = self._load_window(pos, self.variables)
        tr, tm = self._load_window(pos + step, self.variables)

        x = self._standardize_and_impute(xr, xm)
        if self.forcings:
            fr, fm = self._load_window(pos, self.forcings)
            mf = self.x_means[len(self.variables):]
            sf = self.x_stds[len(self.variables):]
            f = np.where(fm, (np.where(fm, fr, 0.0) - mf) / sf, 0.0).astype(np.float32)
            x = np.concatenate([x, f], axis=0)

        if self.residual:
            # Target is the increment from the previous state, in raw units,
            # then scaled by the increment std. Unobserved at either end means
            # no defined increment -> zero, and the loss weight suppresses it.
            if offset > 1:
                pr, pm = self._load_window(pos + (offset - 1) * delta // STEP_HOURS,
                                           self.variables)
            else:
                pr, pm = xr, xm
            both = tm & pm
            d = np.where(both, np.where(both, tr, 0.0) - np.where(both, pr, 0.0), 0.0)
            t = (d / self.t_stds[delta]).astype(np.float32)
        else:
            t = self._standardize_and_impute(tr, tm)

        # Nothing non-finite may leave: a NaN here becomes a NaN loss, becomes
        # NaN gradients, which trainer.py silently zeroes.
        assert np.isfinite(x).all(), f"non-finite input at window {self.times[pos]}"
        assert np.isfinite(t).all(), f"non-finite target at window {self.times[pos]}"

        return (
            (torch.from_numpy(x), torch.from_numpy(t)),
            (idx, torch.tensor(delta / 10.0).float()),
        )


class ERA5ObsRollOutDataset(ERA5ObsDataset):
    """Multi-step targets for online rollout validation.

    Mirrors `ERA5RollOutDataset`: one input state and a stack of targets at
    6h then daily intervals. Targets are returned **unstandardized**, matching
    what `training/validate.py` expects.
    """

    def __init__(self, interval: int, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.interval = interval
        per_day = 24 // STEP_HOURS
        assert self.interval >= per_day, "cannot even predict one day"
        # Only starts with the whole rollout horizon present are usable.
        self._starts = np.array(
            [p for p in self._starts
             if p + self.interval < len(self.files)
             and all(self.files[p + k] is not None
                     for k in range(1, self.interval + 1))],
            dtype=np.int64,
        )
        if self._starts.size == 0:
            raise ValueError(
                f"no window has {self.interval} consecutive frames in split "
                f"'{self.split}'"
            )

    def __getitem__(self, idx: int):
        idx = int(idx)
        pos = int(self._starts[idx])

        xr, xm = self._load_window(pos, self.variables)
        x = torch.from_numpy(self._standardize_and_impute(xr, xm))

        per_day = 24 // STEP_HOURS
        offs = [1] + list(range(per_day, self.interval + 1, per_day))
        ts = []
        for k in offs:
            raw, m = self._load_window(pos + k, self.variables)
            # Unstandardized, and unobserved cells are NaN -- the evaluation is
            # masked, so a filled value would quietly enter the metric.
            ts.append(np.where(m, raw, np.nan))
        t = torch.from_numpy(np.stack(ts, axis=0).astype(np.float32))

        return x, t, idx
