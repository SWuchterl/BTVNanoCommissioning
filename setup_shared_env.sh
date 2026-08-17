#!/bin/bash
# Activates commfw2 -- the single env that can run both this repo (BTVNanoCommissioning,
# coffea 2026.7.0/awkward2) and rabbit (tensorflow-based fitting), now that commfw2 has
# been bumped to numpy==2.2.6 to match rabbit_env and had rabbit's runtime deps
# (tensorflow, tensorflow-probability, wums, h5py) installed into it.
#
# For BTVNanoCommissioning: just activating commfw2 is enough (this repo is pip-installed
# editable into commfw2 already).
# For rabbit: mirrors rabbit/setup.sh (RABBIT_BASE, PYTHONPATH, PATH, XLA_FLAGS), pointed
# at commfw2 instead of rabbit_env.

# commfw2 is a real conda env (unlike rabbit_env, which is a plain venv with its
# own bin/activate) -- needs the conda hook, not `source .../bin/activate`.
eval "$(/eos/home-s/sewuchte/MyConda/condabin/conda shell.bash hook)"
if [ -n "$CONDA_DEFAULT_ENV" ]; then
    conda deactivate
fi

export RABBIT_BASE=$( cd "$( dirname "${BASH_SOURCE[0]}" )/rabbit" && pwd )
export PYTHONPATH="${RABBIT_BASE}"
export PATH="$PATH:${RABBIT_BASE}/bin"

# Enable XLA's multi-threaded Eigen path on CPU. ~1.3x speedup on dense
# large-model HVP/loss+grad on many-core systems, no downside on smaller
# problems. Append to any existing XLA_FLAGS so user-set flags survive.
if [[ ":${XLA_FLAGS:-}:" != *":--xla_cpu_multi_thread_eigen=true:"* ]]; then
    export XLA_FLAGS="${XLA_FLAGS:+$XLA_FLAGS }--xla_cpu_multi_thread_eigen=true"
fi

conda activate commfw2

echo "Activated commfw2 (numpy $(python -c 'import numpy; print(numpy.__version__)') / coffea $(python -c 'import coffea; print(coffea.__version__)')); RABBIT_BASE=${RABBIT_BASE}"
