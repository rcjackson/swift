#!/bin/bash -l
#PBS -l select=1
#PBS -l walltime=06:00:00
#PBS -l place=scatter
#PBS -l filesystems=home:flare
#PBS -q small
#PBS -A Swift-Reanalysis
#PBS -k doe
#PBS -j oe
#PBS -o /lus/flare/projects/Swift-Reanalysis/work/nnja/logs
#PBS -N swift-obs

# Swift on gridded observations. Adapted from aurora-general.sh; the project,
# queue and environment differ (that script targets SAFS and a venv we do not
# have), and this starts at one node on `debug` because the first runs are
# verification, not training.
#
#   qsub -v EXPERIMENT=obs-nnja-swinv2-1.4-scm scripts/aurora-obs.sh
#   qsub -v EXPERIMENT=obs-nnja-swinv2-1.4-scm,LOCAL_BATCH_SIZE=4 scripts/aurora-obs.sh
#
# `small` rather than `debug`: debug caps at 1h and is heavily contended.
# 500 kimg at global batch 48 is ~10.4k optimizer steps; the verification run
# measured ~0.6 s/step per tile, so ~1.7h. 6h of walltime leaves room for a
# slower-than-expected start without wasting the allocation.

echo "Job started at: $(date '+%Y-%m-%d-%H%M%S')"

# frameworks provides torch 2.10 + IPEX. hdf5 is a SEPARATE module and is
# required: the frameworks h5py links libhdf5.so.310, which is not on the
# default library path, and without it `import h5py` fails at import time --
# i.e. the job dies before it reads a single window.
# Note swift_env (anemoi, pyarrow) has no torch and is NOT used for training.
module load frameworks hdf5/1.14.6

# The venv layers swift + its deps over frameworks via --system-site-packages.
source /lus/flare/projects/Swift-Reanalysis/swift/venv/bin/activate

echo "python: $(which python3)"
python3 -c "import torch, h5py; print('torch', torch.__version__, '| h5py', h5py.__version__)"

export http_proxy="http://proxy.alcf.anl.gov:3128"
export https_proxy="http://proxy.alcf.anl.gov:3128"
export ftp_proxy="http://proxy.alcf.anl.gov:3128"

# Aurora / CCL settings, carried over from aurora-general.sh unchanged.
export CCL_KVS_MODE=mpi
export CCL_KVS_CONNECTION_TIMEOUT=600
export PALS_PMI=pmix              # required by Aurora mpich
export CCL_ATL_TRANSPORT=mpi      # required by Aurora mpich

export CCL_OP_SYNC=1
export CCL_ATL_SYNC_COLL=1
export CCL_ENABLE_AUTO_CACHE=0
export CCL_ZE_CACHE_OPEN_IPC_HANDLES_THRESHOLD=4096

export CCL_ALLREDUCE=topo
export CCL_ALLREDUCE_SCALEOUT=direct
export CCL_ALLGATHERV=direct
export CCL_ALLGATHERV_MEDIUM_SIZE_THRESHOLD=0

export FI_CXI_DEFAULT_CQ_SIZE=1048576
export FI_CXI_RX_MATCH_MODE=hybrid
export FI_MR_CACHE_MONITOR=disabled
export FI_CXI_OFLOW_BUF_SIZE=8388608
export FI_CXI_CQ_FILL_PERCENT=30

export CCL_WORKER_AFFINITY=1,9,17,25,33,41,53,61,69,77,85,93
export CPU_BIND="list:2-8:10-16:18-24:26-32:34-40:42-48:54-60:62-68:70-76:78-84:86-92:94-100"
export NUMEXPR_MAX_THREADS=7
export OMP_NUM_THREADS=7

cd /lus/flare/projects/Swift-Reanalysis/swift
echo "Current working directory: $(pwd)"

source <(curl -s https://raw.githubusercontent.com/saforem2/ezpz/refs/heads/main/src/ezpz/bin/utils.sh)
ezpz_setup_env

: ${EXPERIMENT:=obs-nnja-swinv2-1.4-scm}
: ${LOCAL_BATCH_SIZE:=4}

: ${PARTID:=0}
PARTID=$(printf "%03d" "$PARTID")
if [[ "$PARTID" == "000" ]]; then
  resume=null
else
  resume=$(printf "%03d" $((10#$PARTID - 1)))
fi

export HYDRA_FULL_ERROR=1
export HYDRA_RUN_ID=$PARTID
BATCH_SIZE=$((num_gpus * LOCAL_BATCH_SIZE))

echo "EXPERIMENT=$EXPERIMENT  PARTID=$PARTID  global batch=$BATCH_SIZE"

run_cmd="${DIST_LAUNCH} python3 -m swift.train \
    experiment=${EXPERIMENT} \
    data.batch_size=${BATCH_SIZE} \
    resume=${resume}"

eval "${run_cmd}"
