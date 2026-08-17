#!/bin/bash -x

JOBID=$1
NCPU=$2

# Phase timing markers -- grep 'PHASE' out of the condor .out to attribute
# wall time to setup / extract / processing / stage-out.
PHASE_T0=$(date +%s)
PHASE_TPREV=$PHASE_T0
phase() {
    local now=$(date +%s)
    echo "PHASE $1 elapsed=$((now - PHASE_TPREV))s total=$((now - PHASE_T0))s"
    PHASE_TPREV=$now
}

export HOME=`pwd`
if [ -d /afs/cern.ch/user/${USER:0:1}/$USER ]; then
  export HOME=/afs/cern.ch/user/${USER:0:1}/$USER  # crucial on lxplus condor but cannot set on cmsconnect
fi
env


WORKDIR=`pwd`

# Get arguments
declare -A ARGS
for key in workflow output samplejson year campaign isSyst ttbar_reweights isArray array_systs noHist overwrite voms chunk skipbadfiles outputDir remoteRepo; do
    echo $(jq -r ".$key" $WORKDIR/arguments.json)
    ARGS[$key]=$(jq -r ".$key" $WORKDIR/arguments.json)
done

# Set up mamba environment
## Interactive bash script with fallback pointing to $HOME, hence setting $PWD of worker node as $HOME
export HOME=`pwd`

echo "Setting up mamba environment"
if [[ ${ARGS[remoteRepo]} != "" ]]; then
    echo "remoteRepo is set to ${ARGS[remoteRepo]}"
    for i in {1..10}; do
        wget --timeout=20 --tries=1 -L micro.mamba.pm/install.sh
        if [ $? -eq 0 ]; then
            break
        fi
	echo "Failed attempt #"$i" to download mamba installer. Will retry."
        sleep 30
    done
    chmod +x install.sh
    ## FIXME parsing arguments does not work. will use defaults in install.sh instead, see https://github.com/mamba-org/micromamba-releases/blob/main/install.sh 
    ## Tried solutions listed in https://stackoverflow.com/questions/14392525/passing-arguments-to-an-interactive-program-non-interactively
    ./install.sh <<< $'bin\nY\nY\nmicromamba\n' 
    source .bashrc
fi

export PATH=$WORKDIR:$PATH

if [ ! -d /afs/cern.ch/user/${USER:0:1}/$USER ]; then
    ## install necessary packages if on cmsconnect
    micromamba install -c conda-forge jq --yes || { echo "ERROR: micromamba install of jq failed."; exit 1; }
fi

# Create base env with python=3.10 and setuptools<=70.1.1
micromamba activate
micromamba install python=3.10 -c conda-forge xrootd --yes || { echo "ERROR: micromamba install of python/xrootd failed."; exit 1; }
micromamba activate base
micromamba install setuptools=70.1.1 || { echo "ERROR: micromamba install of setuptools failed."; exit 1; }
phase mamba

# Install BTVNanoCommissioning
mkdir BTVNanoCommissioning
cd BTVNanoCommissioning
if [ ! -f $WORKDIR/BTVNanoCommissioning.tar.gz ]; then
    ## clone the BTVNanoCommissioning repo only, no submodule
    git clone ${ARGS[remoteRepo]} . || { echo "ERROR: git clone of ${ARGS[remoteRepo]} failed."; exit 1; }
else
    tar xaf $WORKDIR/BTVNanoCommissioning.tar.gz || { echo "ERROR: extracting BTVNanoCommissioning.tar.gz failed."; exit 1; }
fi
phase extract

pip install -e . || { echo "ERROR: pip install -e . failed."; exit 1; }

## other dependencies
pip install psutil || { echo "ERROR: pip install psutil failed."; exit 1; }
phase pip

# Build the sample json given the job id
python -c "import json, os; flname = 'split_samples.json' if os.path.isfile(f'$WORKDIR/split_samples.json') else 'split_samples_resubmit.json';  json.dump(json.load(open(f'$WORKDIR/{flname}'))['$JOBID'], open('$WORKDIR/sample.json', 'w'), indent=4)"
cp $WORKDIR/sample.json $WORKDIR/BTVNanoCommissioning/sample.json

ls -lah $WORKDIR
ls -lah $WORKDIR/BTVNanoCommissioning

# Unparse arguments and send to runner.py
OPTS="--wf ${ARGS[workflow]} --year ${ARGS[year]} --campaign ${ARGS[campaign]} --chunk ${ARGS[chunk]}"
if [ "${ARGS[voms]}" != "null" ]; then
    OPTS="$OPTS --voms ${ARGS[voms]}"
fi
if [ "${ARGS[isSyst]}" != "false" ]; then
    OPTS="$OPTS --isSyst ${ARGS[isSyst]}"
fi
if [ "${ARGS[ttbar_reweights]}" != "none" ]; then
    OPTS="$OPTS --ttbar-reweights ${ARGS[ttbar_reweights]}"
fi
if [ "${ARGS[array_systs]}" != "none" ] && [ "${ARGS[array_systs]}" != "null" ]; then
    OPTS="$OPTS --array-systs ${ARGS[array_systs]}"
fi
for key in  isArray noHist overwrite skipbadfiles; do
    if [ "${ARGS[$key]}" == true ]; then
        OPTS="$OPTS --$key"
    fi
done
OPTS="$OPTS --output ${ARGS[output]//.coffea/_$JOBID.coffea}"  # add a suffix to output file name
OPTS="$OPTS --json sample.json"  # use the sample json for this JOBID

# Check the number of CPUs requested and set the worker accordingly.
# If nCPU > 1, use futures executor with nCPU workers. If nCPU = 1, use iterative executor with 1 worker.
if [ $NCPU -gt 1 ]; then
    OPTS="$OPTS --worker $NCPU"  # use number of worker = nCPU
    OPTS="$OPTS --executor futures"
else
    OPTS="$OPTS --worker 1"  # use number of worker = 1
    OPTS="$OPTS --executor iterative"
fi

# Launch
echo "Now launching: python runner.py $OPTS"
python runner.py $OPTS
RUNNER_RC=$?
phase runner
if [ $RUNNER_RC -ne 0 ]; then
    echo "ERROR: runner.py failed -- not transferring output or marking success."
    exit 1
fi

# Transfer output
if [[ ${ARGS[outputDir]} == root://* ]]; then

    xrdcp --silent -p -f -r hists_* ${ARGS[outputDir]}/
    if [ $? -ne 0 ]; then
        echo "ERROR: xrdcp of hists_* to ${ARGS[outputDir]} failed."
        exit 1
    fi
    if [[ "$OPTS" == *"isArray"* ]]; then
	xrdcp --silent -p -f -r arrays_* ${ARGS[outputDir]}/
	if [ $? -ne 0 ]; then
	    echo "ERROR: xrdcp of arrays_* to ${ARGS[outputDir]} failed."
	    exit 1
	fi
    fi
else
    mkdir -p ${ARGS[outputDir]}
    cp -p -f -r hists_* ${ARGS[outputDir]}/
    if [ $? -ne 0 ]; then
        echo "ERROR: cp of hists_* to ${ARGS[outputDir]} failed."
        exit 1
    fi
    if [[ "$OPTS" == *"isArray"* ]]; then
	cp -p -f -r arrays_* ${ARGS[outputDir]}/
	if [ $? -ne 0 ]; then
	    echo "ERROR: cp of arrays_* to ${ARGS[outputDir]} failed."
	    exit 1
	fi
    fi
fi
phase stageout

### one can also consider origanizing the root files in the subdirectory structure ###
# for filename in `\ls *.root`; do
#     SAMPLENAME=$(echo "$filename" | sed -E 's/(.*)_f[0-9-]+_[0-9]+\.root/\1/')
#     # SAMPLENAME=$(echo "$filename" | sed -E 's/(.*)_[0-9a-z]{9}-[0-9a-z]{4}-.*\.root/\1/')
#     xrdcp --silent -p -f $filename ${ARGS[outputDir]}/$SAMPLENAME/
# done

touch $WORKDIR/.success
