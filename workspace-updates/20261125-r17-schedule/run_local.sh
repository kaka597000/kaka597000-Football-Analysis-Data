#!/bin/sh
set -eu
export NPY_DISABLE_CPU_FEATURES=AVX512F
export OPENBLAS_CORETYPE=Haswell
export OPENBLAS_NUM_THREADS=1
export OMP_NUM_THREADS=1
exec python "$(dirname "$0")/build.py" "$@"
