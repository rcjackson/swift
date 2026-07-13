"""Grid anemoi *tabular* observations onto the Swift state grid.

Reads an anemoi-datasets tabular observation dataset windowed to the model cadence
and bins each window onto the state's ``(latitude, longitude)`` grid, producing a
gridded zarr with, per observation variable, a value channel ``<var>`` and a
companion mask channel ``<var>_mask`` (1 where at least one observation fell in the
cell, else 0). The ``time`` axis is positionally aligned with the sorted split
files so :class:`swift.data.obs.ObsForecastDataset` can index it directly.

Usage:

    python -m swift.data.grid_obs \
        --obs_dataset /path/to/obs-surface.zarr \
        --state_root  /lus/flare/.../1.40625deg_1_step_6hr_h5df \
        --split       train \
        --output      /lus/flare/.../obs \
        --name        obs-surface \
        --obs_variables 2t 2d msl 10u 10v sst \
        --window "(-6h,0]" --frequency 6h
"""

import argparse
import os
from glob import glob

import h5py
import numpy as np
import xarray as xr
import zarr
from scipy.stats import binned_statistic_2d
from tqdm import tqdm

parser = argparse.ArgumentParser()
parser.add_argument("--obs_dataset", required=True, help="anemoi tabular dataset path")
parser.add_argument("--state_root", required=True, help="state h5df root (lat/lon + split)")
parser.add_argument("--split", default="train", choices=["train", "val", "test"])
parser.add_argument("--output", required=True, help="output directory for the obs zarr")
parser.add_argument("--name", required=True, help="obs zarr name (e.g. obs-surface)")
parser.add_argument("--obs_variables", nargs="+", required=True)
parser.add_argument("--window", default="(-6h,0]")
parser.add_argument("--frequency", default="6h")


def _edges_from_centers(centers: np.ndarray) -> np.ndarray:
    """Bin edges from monotonically increasing cell centers."""
    mids = (centers[:-1] + centers[1:]) / 2.0
    first = centers[0] - (mids[0] - centers[0])
    last = centers[-1] + (centers[-1] - mids[-1])
    return np.concatenate([[first], mids, [last]])


def _match_lon(lon: np.ndarray, lon_grid: np.ndarray) -> np.ndarray:
    """Map observation longitudes into the state grid's longitude convention."""
    if lon_grid.min() >= 0.0:  # state grid uses [0, 360)
        return np.where(lon < 0.0, lon + 360.0, lon)
    return np.where(lon > 180.0, lon - 360.0, lon)  # state grid uses [-180, 180]


def _state_split_times(state_root: str, split: str) -> np.ndarray:
    files = sorted(glob(os.path.join(state_root, split, "*.h5")))
    assert files, f"no state .h5 files under {state_root}/{split}"

    def _t(path):
        with h5py.File(path, "r") as f:
            return np.datetime64(f["input"]["time"][()].decode("utf-8"))

    return np.array([_t(files[0]), _t(files[-1])]), len(files)


def main(args):
    from anemoi.datasets import open_dataset

    lat = np.load(os.path.join(args.state_root, "lat.npy")).astype(np.float32)
    lon = np.load(os.path.join(args.state_root, "lon.npy")).astype(np.float32)
    n_lat, n_lon = len(lat), len(lon)
    lat_edges = _edges_from_centers(lat)
    lon_edges = _edges_from_centers(lon)

    (t0, t1), n_files = _state_split_times(args.state_root, args.split)

    ds = open_dataset(
        args.obs_dataset,
        start=str(t0),
        end=str(t1),
        window=args.window,
        frequency=args.frequency,
    )
    assert len(ds) == n_files, (
        f"windowed obs length ({len(ds)}) != state files ({n_files}); "
        "check start/end/frequency alignment with the split"
    )

    # column index of each requested observation variable
    var_index = {v: i for i, v in enumerate(ds.variables)}
    missing = [v for v in args.obs_variables if v not in var_index]
    assert not missing, f"variables not in obs dataset: {missing}"
    cols = [var_index[v] for v in args.obs_variables]

    # reference dates aligned with the state split (integer-position indexed)
    time_coord = np.arange(
        np.datetime64(t0, "ns"),
        np.datetime64(t1, "ns") + np.timedelta64(1, "ns"),
        np.timedelta64(int(args.frequency.rstrip("h")), "h"),
    )
    assert len(time_coord) == n_files, "frequency does not tile the split evenly"

    ofile = os.path.join(args.output, f"{args.name}.zarr", args.split)
    os.makedirs(os.path.dirname(ofile), exist_ok=True)

    coords = {
        "time": (("time",), time_coord),
        "latitude": (("latitude",), lat),
        "longitude": (("longitude",), lon),
    }
    xr.Dataset(coords=coords).to_zarr(ofile, mode="w")

    dims = ["time", "latitude", "longitude"]
    with zarr.open_group(ofile, mode="a") as g:
        arrays = {}
        for v in args.obs_variables:
            for name, dtype, fill in ((v, "f4", 0.0), (f"{v}_mask", "f4", 0.0)):
                a = g.create_dataset(
                    name,
                    shape=(n_files, n_lat, n_lon),
                    chunks=(1, n_lat, n_lon),
                    dtype=dtype,
                    fill_value=fill,
                )
                a.attrs["_ARRAY_DIMENSIONS"] = dims
                arrays[name] = a

        for i in tqdm(range(len(ds)), desc=f"grid {args.split}"):
            sample = ds[i]  # [n_obs, n_vars]
            n_obs = sample.shape[0]
            if n_obs == 0:
                continue  # empty window -> value 0, mask 0 (fill values)
            olat = np.asarray(sample.latitudes, dtype=np.float64)
            olon = _match_lon(np.asarray(sample.longitudes, dtype=np.float64), lon)
            data = np.asarray(sample, dtype=np.float64)

            for v, c in zip(args.obs_variables, cols):
                vals = data[:, c]
                finite = np.isfinite(vals) & np.isfinite(olat) & np.isfinite(olon)
                if not finite.any():
                    continue
                mean, _, _, _ = binned_statistic_2d(
                    olat[finite], olon[finite], vals[finite],
                    statistic="mean", bins=[lat_edges, lon_edges],
                )
                count, _, _, _ = binned_statistic_2d(
                    olat[finite], olon[finite], vals[finite],
                    statistic="count", bins=[lat_edges, lon_edges],
                )
                mask = (count > 0).astype("f4")
                mean = np.nan_to_num(mean, nan=0.0).astype("f4")  # empty cells -> 0
                arrays[v][i] = mean
                arrays[f"{v}_mask"][i] = mask

    zarr.consolidate_metadata(ofile)
    print(f"Wrote gridded obs to {ofile}")


if __name__ == "__main__":
    main(parser.parse_args())
