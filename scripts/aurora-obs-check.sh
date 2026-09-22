#!/bin/bash -l
#PBS -l select=1
#PBS -l walltime=00:30:00
#PBS -l place=scatter
#PBS -l filesystems=home:flare
#PBS -q debug
#PBS -A Swift-Reanalysis
#PBS -k doe
#PBS -j oe
#PBS -o /lus/flare/projects/Swift-Reanalysis/work/nnja/logs
#PBS -N swift-obs-check

# Verification rungs 2-4 before committing to a training run. Runs on a compute
# node because importing the model pulls in MPI, which cannot init on a login
# node ("Fatal error in internal_Init_thread").
#
#   qsub scripts/aurora-obs-check.sh

echo "Job started at: $(date '+%Y-%m-%d-%H%M%S')"

module load frameworks hdf5/1.14.6
source /lus/flare/projects/Swift-Reanalysis/swift/venv/bin/activate

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
echo "python: $(which python3)"
python3 -c "import torch, h5py; print('torch', torch.__version__, '| h5py', h5py.__version__)"

# single rank is enough -- this checks numerics, not scaling
python3 /lus/flare/projects/Swift-Reanalysis/work/nnja/overfit_check.py
echo "EXIT=$?"
