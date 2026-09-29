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
# Usage:
#   qsub -v CHECKPOINT=/abs/path/checkpoint-003400.pt scripts/aurora-obs-eval.sh
#   qsub -v CHECKPOINT=...,LIMIT=50 scripts/aurora-obs-eval.sh   # quick smoke
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

if [ -z "$CHECKPOINT" ]; then
  echo "FATAL: pass -v CHECKPOINT=/abs/path/to/checkpoint-NNNNNN.pt" >&2
  exit 1
fi
if [ ! -f "$CHECKPOINT" ]; then
  echo "FATAL: no such checkpoint: $CHECKPOINT" >&2
  exit 1
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
echo "CHECKPOINT=$CHECKPOINT"
echo "SPLIT=$SPLIT  DELTA=${DELTA}h  INIT_HOURS=$INIT_HOURS  LIMIT=$LIMIT"
echo "VARS=$(echo $VARS | tr ',' '\n' | wc -l) variables"

python3 /lus/flare/projects/Swift-Reanalysis/work/nnja/eval_masked.py \
    --root "$ROOT" \
    --split "$SPLIT" \
    --delta "$DELTA" \
    --init-hours "$INIT_HOURS" \
    --experiment "$EXPERIMENT" \
    --checkpoint "$CHECKPOINT" \
    --variables "$VARS" \
    --limit "$LIMIT"
RC=$?

echo
echo "eval exit code: $RC"
exit $RC
