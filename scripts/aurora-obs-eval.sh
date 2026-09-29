#!/bin/bash -l
#PBS -l select=1
#PBS -l walltime=01:00:00
#PBS -l place=scatter
#PBS -l filesystems=home:flare
#PBS -q debug
#PBS -A Swift-Reanalysis
#PBS -k doe
#PBS -j oe
#PBS -o /lus/flare/projects/Swift-Reanalysis/work/nnja/logs
#PBS -N swift-obs-eval
#PBS -M rjackson@anl.gov
#PBS -m ae

# Masked-RMSE scoring of a trained checkpoint (work/nnja/eval_masked.py).
#
# WHY THIS NEEDS A JOB AT ALL: eval_masked.py imports ezpz to get a torch
# device, and importing ezpz initializes MPI -- which cannot be done from a
# login node. One node is enough; scoring is a single-rank loop over the test
# windows, and DIST_LAUNCH is deliberately NOT used.
#
# WHY THIS IS THE METRIC THAT COUNTS: the in-training `val/rmse` from
# training/validate.py averages over EVERY grid cell, and on observation grids
# ~89% of cells were never observed and hold imputed climatology -- so that
# number mostly scores the model against its own filler. Reading a trend into
# it once led to killing a healthy training chain. This script scores observed
# cells only, against two baselines: persistence, and a per-cell diurnal
# climatology fitted on the TRAIN split. Persistence is the weak bar; the
# diurnal column is the real one, because a model that beats only persistence
# has not necessarily learned anything a lookup table could not do.
#
# TWO JOBS, NOT ONE. `debug` caps walltime at 1h (hard -- resources_max), and
# fitting the diurnal-climatology baseline on the 69-variable train split takes
# ~30 min of that. So warm the cache first, then score:
#
#   qsub -v CHECKPOINT= scripts/aurora-obs-eval.sh                # ~35 min
#   qsub -v CHECKPOINT=/abs/path/checkpoint-003400.pt scripts/aurora-obs-eval.sh
#
# Only the first is slow; the cache is keyed on root/split/delta/init_hours/
# variables and is reused by every later checkpoint. Add LIMIT=50 for a smoke
# test. Note `debug` allows ONE queued job per user, so submit them in order,
# not as a pair.
#
# VARS defaults to all 69 in the data config's ORDER. That order is not
# cosmetic: eval_masked.py builds the net with img_channels=ds.n_target_channels
# and then load_state_dict()s the checkpoint, so a short or reordered list
# builds the wrong net and either fails the load or silently scores the wrong
# channel against the wrong target.

echo "Job started at: $(date '+%Y-%m-%d-%H%M%S')"

# See scripts/aurora-obs-scaling.sh for the full note: on 2026-09-29 the Aurora
# default module tree rolled 26.26.0 -> 26.181.0 and torch stopped importing
# (libmkl_intel_lp64.so.2 missing). Pinning frameworks alone is NOT enough --
# oneapi is what puts MKL on LD_LIBRARY_PATH. Both are pinned.
module load oneapi/release/2025.3.1
module load frameworks/2025.3.1 hdf5/1.14.6

source /lus/flare/projects/Swift-Reanalysis/swift/venv/bin/activate

echo "python: $(which python3)"
python3 -c "import torch, h5py; print('torch', torch.__version__, '| h5py', h5py.__version__)"
if [ $? -ne 0 ]; then
  echo "FATAL: torch/h5py import failed -- check the module pins above" >&2
  module list
  exit 1
fi

export http_proxy="http://proxy.alcf.anl.gov:3128"
export https_proxy="http://proxy.alcf.anl.gov:3128"
export ftp_proxy="http://proxy.alcf.anl.gov:3128"

export CCL_KVS_MODE=mpi
export CCL_KVS_CONNECTION_TIMEOUT=600
export PALS_PMI=pmix
export CCL_ATL_TRANSPORT=mpi
export NUMEXPR_MAX_THREADS=7
export OMP_NUM_THREADS=7

cd /lus/flare/projects/Swift-Reanalysis/swift
echo "Current working directory: $(pwd)"

source <(curl -s https://raw.githubusercontent.com/saforem2/ezpz/refs/heads/main/src/ezpz/bin/utils.sh)
ezpz_setup_env

: ${EXPERIMENT:=obs-nnja-11y-69v-swinv2-1.4-scm}
: ${ROOT:=/lus/flare/projects/Swift-Reanalysis/work/nnja/swift_root_69v}
: ${SPLIT:=test}
: ${DELTA:=12}
: ${INIT_HOURS:=0,12}
: ${LIMIT:=0}

# CHECKPOINT="" is legal and means "baselines only". That is the cache-warming
# mode: the diurnal climatology is fitted on the train split and does not
# depend on the checkpoint, but it costs ~30 min on the 69-variable root --
# over half a debug job, before the model is touched. Warm it once:
#
#   qsub -v CHECKPOINT= scripts/aurora-obs-eval.sh        # ~35 min, caches
#   qsub -v CHECKPOINT=/abs/path.pt scripts/aurora-obs-eval.sh   # then scores
#
# The second job reads the cache in seconds and spends its hour on the model.
if [ -n "$CHECKPOINT" ] && [ ! -f "$CHECKPOINT" ]; then
  echo "FATAL: no such checkpoint: $CHECKPOINT" >&2
  exit 1
fi
CKARG=()
if [ -n "$CHECKPOINT" ]; then
  CKARG=(--checkpoint "$CHECKPOINT")
else
  echo "NOTE: no CHECKPOINT given -- baselines only (warms the climatology cache)"
fi

# All 69, in data-config order. Built from the config itself rather than
# retyped, so the two cannot drift apart.
: ${VARS:=$(python3 - <<'PYV'
import re
p = "src/swift/configs/data/obs-nnja-11y-69v-1.4.yaml"
txt = open(p).read()
body = txt.split("variables:", 1)[1].split("forcings:", 1)[0]
v = [m.group(1) for m in re.finditer(r"^\s+-\s+(\S+)\s*$", body, re.M)]
assert len(v) == 69, f"expected 69 variables, got {len(v)}"
print(",".join(v))
PYV
)}
if [ -z "$VARS" ]; then
  echo "FATAL: could not build the variable list from the data config" >&2
  exit 1
fi

echo "EXPERIMENT=$EXPERIMENT"
echo "CHECKPOINT=${CHECKPOINT:-<none, baselines only>}"
echo "SPLIT=$SPLIT  DELTA=${DELTA}h  INIT_HOURS=$INIT_HOURS  LIMIT=$LIMIT"
echo "VARS=$(echo $VARS | tr ',' '\n' | wc -l) variables"

# -u: without it stdout block-buffers into the PBS log and a job that is
# working normally looks hung for tens of minutes -- which is exactly how
# job 8879154 read before it was diagnosed.
python3 -u /lus/flare/projects/Swift-Reanalysis/work/nnja/eval_masked.py \
    --root "$ROOT" \
    --split "$SPLIT" \
    --delta "$DELTA" \
    --init-hours "$INIT_HOURS" \
    --experiment "$EXPERIMENT" \
    "${CKARG[@]}" \
    --variables "$VARS" \
    --limit "$LIMIT"
RC=$?

echo
echo "eval exit code: $RC"
exit $RC
