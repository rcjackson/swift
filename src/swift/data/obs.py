import os
from typing import Tuple

import numpy as np
import torch
import xarray as xr

from swift.data.era5 import ERA5Dataset


class ObsForecastDataset(ERA5Dataset):
    """Observation-only, direct N-step forecasting dataset.

    The *condition* fed to the model is gridded observations (a value channel and
    a companion mask channel per observation variable). The *target* is the full
    future ERA5 state at ``idx + delta // 6`` (no residual, no state input, no
    autoregression). Lead time ``delta`` is carried by the ``auxiliary`` embedding,
    exactly as in :class:`ERA5Dataset`.

    State loading, standardization and grid properties are inherited from
    :class:`ERA5Dataset` and used for the *target* only. Observations are read from
    a separate gridded zarr (produced by ``swift.data.grid_obs``) whose ``time``
    axis is positionally aligned with the sorted split files.
    """

    def __init__(
        self,
        root: str,
        variables: list[str],
        obs_zarr: str,
        obs_variables: list[str],
        obs_stats_dir: str | None = None,
        intervals: list[int] = [6, 12],
        split: str = "train",
        dropout_p: float = 0.0,
        **kwargs,
    ):
        # Observations are the only input: no forcings, never a residual target.
        kwargs.pop("forcings", None)
        kwargs.pop("residual", None)
        super().__init__(
            root=root,
            variables=variables,
            forcings=[],
            intervals=intervals,
            split=split,
            residual=False,
        )

        self.split = split  # ERA5Dataset does not retain this
        self.obs_variables = obs_variables
        self.dropout_p = dropout_p
        # obs stats live alongside the state stats unless overridden
        self.obs_stats_dir = obs_stats_dir or root
        self.obs_means, self.obs_stds = self._setup_obs_standardize()

        # obs zarr resolved per split; opened lazily so DataLoader workers each get
        # their own handle after fork.
        per_split = os.path.join(obs_zarr, split)
        self._obs_zarr_path = per_split if os.path.exists(per_split) else obs_zarr
        self._obs_ds: xr.Dataset | None = None

    # ------------------------------------------------------------------ setup

    def _setup_obs_standardize(self) -> Tuple[np.ndarray, np.ndarray]:
        """Per-variable value-channel mean/std, shaped (V, 1, 1) for broadcasting."""
        means = self._load_obs_stack("obs_normalize_mean.npz", self.obs_variables)
        stds = self._load_obs_stack("obs_normalize_std.npz", self.obs_variables)
        return means, stds

    def _load_obs_stack(self, filename: str, variables: list[str]) -> np.ndarray:
        """Load obs stats from ``obs_stats_dir`` (kept separate from the inherited
        ``_load_and_stack`` which reads state stats from ``root``)."""
        with np.load(os.path.join(self.obs_stats_dir, filename)) as data:
            return np.stack([data[v] for v in variables], axis=0).reshape(-1, 1, 1)

    def _obs(self) -> xr.Dataset:
        if self._obs_ds is None:
            self._obs_ds = xr.open_zarr(self._obs_zarr_path, consolidated=True)
            assert self._obs_ds.sizes["time"] == len(self.files), (
                f"obs zarr time ({self._obs_ds.sizes['time']}) must align with "
                f"{len(self.files)} state files for split '{self.split}'"
            )
        return self._obs_ds

    # ------------------------------------------------------------- properties

    @property
    def n_condition_channels(self) -> int:
        # value + mask per observation variable
        return 2 * len(self.obs_variables)

    # ------------------------------------------------- target standardization

    def standardize_t(self, t, delta: int = 6):
        # obs-forecast is never residual: the target is the full state, standardized
        # with the state stats (forcings are empty, so x_means == state stats).
        t = self._transform_standardize(t, self.x_means, self.x_stds)
        return self.zero_field(t, delta)

    def unstandardize_t(self, t, delta: int = 6):
        t = self._transform_standardize(t, self.x_means, self.x_stds, inverse=True)
        return self.zero_field(t, delta)

    # -------------------------------------------------------------- accessors

    def _load_obs(self, idx: int) -> Tuple[np.ndarray, np.ndarray]:
        """Return (values, mask) each of shape (V, H, W) for reference time idx."""
        t = self._obs().isel(time=idx)
        values = np.stack(
            [np.asarray(t[v].values, dtype=np.float32) for v in self.obs_variables],
            axis=0,
        )
        mask = np.stack(
            [
                np.asarray(t[f"{v}_mask"].values, dtype=np.float32)
                for v in self.obs_variables
            ],
            axis=0,
        )
        return values, mask

    def standardize_obs(self, values: np.ndarray, mask: np.ndarray) -> np.ndarray:
        """Masked standardization: neutral (0) wherever no observation is present."""
        std = (values - self.obs_means) / self.obs_stds
        return (std * mask).astype(np.float32)

    def _apply_dropout(self, values: np.ndarray, mask: np.ndarray) -> None:
        """Randomly drop whole observation variables (simulates missing instruments)."""
        if self.dropout_p <= 0.0:
            return
        drop = np.random.random(len(self.obs_variables)) < self.dropout_p
        # never drop everything — the model must always see some observations
        if drop.all():
            drop[np.random.randint(len(drop))] = False
        values[drop] = 0.0
        mask[drop] = 0.0

    # ---------------------------------------------------------------- getitem

    def __getitem__(
        self, spec: int | tuple[int, int] | tuple[int, int, int]
    ) -> Tuple[Tuple[torch.Tensor, torch.Tensor], Tuple[int, torch.Tensor]]:
        if isinstance(spec, tuple):
            spec = tuple(int(i) for i in spec)
        else:
            spec = int(spec)

        match spec:
            case int() as idx:
                delta = None
            case (int() as idx, int() as _off):
                delta = None
            case (int() as idx, int() as _off, int() as d):
                delta = d
            case _:
                raise ValueError(f"Invalid index spec: {spec!r}")

        if delta is None:
            delta = int(np.random.choice(self.intervals))

        # condition: gridded observations at the reference time (obs-only input)
        values, mask = self._load_obs(idx)
        self._apply_dropout(values, mask)
        condition = np.concatenate([self.standardize_obs(values, mask), mask], axis=0)

        # target: full future state (no residual, no state input)
        target = self._load_file(self.files[idx + delta // 6], self.variables)
        target = self.standardize_t(target, delta)

        x = torch.from_numpy(condition).float()  # 2V x H x W
        t = torch.from_numpy(np.ascontiguousarray(target)).float()  # C x H x W
        return (x, t), (idx, torch.tensor(delta / 10.0).float())
