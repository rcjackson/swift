"""Compute normalization statistics for gridded observations.

For each observation *value* channel, the mean/std are computed over **observed
cells only** (mask == 1), streamed over time to bound memory. Results are written
as ``obs_normalize_mean.npz`` / ``obs_normalize_std.npz`` with one scalar per
variable — the form expected by
:meth:`swift.data.obs.ObsForecastDataset._load_obs_stack`.

Mask channels are intentionally not standardized (the dataset passes them through
as 0/1), so no stats are produced for them.

Usage:

    python -m swift.data.compute_obs_stats \
        --obs_zarr /lus/flare/.../obs/obs-surface.zarr \
        --split train \
        --obs_variables 2t 2d msl 10u 10v sst \
        --output /lus/flare/.../1.40625deg_1_step_6hr_h5df
"""

import argparse
import os

import numpy as np
import xarray as xr
from tqdm import tqdm

parser = argparse.ArgumentParser()
parser.add_argument("--obs_zarr", required=True, help="gridded obs zarr (from grid_obs)")
parser.add_argument("--split", default="train", help="split to compute stats over")
parser.add_argument("--obs_variables", nargs="+", required=True)
parser.add_argument("--output", required=True, help="dir to write obs_normalize_*.npz")


def main(args):
    path = os.path.join(args.obs_zarr, args.split)
    if not os.path.exists(path):
        path = args.obs_zarr
    ds = xr.open_zarr(path, consolidated=True)

    n = ds.sizes["time"]
    count = {v: 0.0 for v in args.obs_variables}
    ssum = {v: 0.0 for v in args.obs_variables}
    ssq = {v: 0.0 for v in args.obs_variables}

    for i in tqdm(range(n), desc="obs stats"):
        t = ds.isel(time=i)
        for v in args.obs_variables:
            mask = np.asarray(t[f"{v}_mask"].values, dtype=bool)
            if not mask.any():
                continue
            vals = np.asarray(t[v].values, dtype=np.float64)[mask]
            vals = vals[np.isfinite(vals)]
            count[v] += vals.size
            ssum[v] += vals.sum()
            ssq[v] += np.square(vals).sum()

    means, stds = {}, {}
    for v in args.obs_variables:
        if count[v] == 0:
            raise ValueError(f"no observed cells for '{v}' in split '{args.split}'")
        mean = ssum[v] / count[v]
        var = max(ssq[v] / count[v] - mean * mean, 0.0)
        std = np.sqrt(var)
        means[v] = np.float32(mean)
        # guard against degenerate/constant channels
        stds[v] = np.float32(std if std > 1e-6 else 1.0)

    os.makedirs(args.output, exist_ok=True)
    np.savez(os.path.join(args.output, "obs_normalize_mean.npz"), **means)
    np.savez(os.path.join(args.output, "obs_normalize_std.npz"), **stds)
    print(f"Wrote obs stats for {len(means)} variables to {args.output}")
    for v in args.obs_variables:
        print(f"  {v}: mean={means[v]:.4g} std={stds[v]:.4g} n={int(count[v])}")


if __name__ == "__main__":
    main(parser.parse_args())
