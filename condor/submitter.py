import os, sys
import json
import shutil
import tarfile
import argparse


def _prompt_yn(prompt):
    # Scripts (e.g. 02_run_workflows.sh) call this submitter multiple times
    # in a row non-interactively; stdin has no input to give, so input()
    # would raise EOFError. Match what happens if a human just hits enter --
    # the prompts' bracketed "[y]" default -- instead of crashing.
    try:
        return input(prompt)
    except EOFError:
        return ""


def make_tarfile(output_filename, source_dir, exclude_dirs=[]):
    with tarfile.open(output_filename, "w:gz") as tar:
        for root, dirs, files in os.walk(source_dir):
            dirs[:] = [
                d for d in dirs if d not in exclude_dirs
            ]  # Exclude specified directories
            for file in files:
                file_path = os.path.join(root, file)
                # Never nest the sandbox tarball inside itself: skip the file we
                # are writing plus any stale copy at the top of source_dir.
                # Matched by exact path, not a "*.tar.gz" glob -- that would
                # also drop the JME Summer23/23BPix payloads under data/.
                if os.path.abspath(file_path) in (
                    os.path.abspath(output_filename),
                    os.path.abspath(
                        os.path.join(source_dir, "BTVNanoCommissioning.tar.gz")
                    ),
                ):
                    continue
                tar.add(file_path, arcname=os.path.relpath(file_path, source_dir))


def get_condor_submitter_parser(parser):
    parser.add_argument(
        "--jobName",
        help="Condor job name to make the job directory",
        required=True,
    )
    parser.add_argument(
        "-nCPU",
        "--nCPU",
        default=1,
        type=int,
        help="Number of CPUs to request for each condor job (default: %(default)s). Job memory scales as nCPU*3GB, adjust if necessary.",
    )
    parser.add_argument(
        "-n",
        "--condorFileSize",
        type=int,
        default=50,
        help="Number of files proceed per condor job (default: %(default)s)",
    )
    parser.add_argument(
        "--outputDir",
        help="Output directory",
        required=True,
    )
    parser.add_argument(
        "--remoteRepo",
        default=None,
        help="If specified, access BTVNanoCommsioning from a remote tarball (downloaded via https), instead of from a transferred sandbox",
    )
    parser.add_argument(
        "--jobqueue",
        default="tomorrow",
        help="JobFlavour for condor@lxplus. E.g. microcentury, longlunch, workday, tomorrow",
    )
    parser.add_argument(
        "--accountingGroup",
        default=None,
        help="If specified, sets +AccountingGroup in the JDL (e.g. group_u_CMST3.all) for priority/quota purposes",
    )
    return parser


def get_main_parser():
    parser = argparse.ArgumentParser(description="Arguments for condor submitter")
    ## Inputs
    parser.add_argument(
        "--wf",
        "--workflow",
        dest="workflow",
        help="Which processor to run",
        required=True,
    )
    parser.add_argument(
        "-o",
        "--output",
        default=r"hists.coffea",
        help="Output histogram filename (default: %(default)s)",
    )
    parser.add_argument(
        "--samples",
        "--json",
        dest="samplejson",
        nargs="+",
        default="dummy_samples.json",
        help="JSON file containing dataset and file locations (default: %(default)s)",
    )
    ## Configuations
    parser.add_argument("--year", default="2023", help="Year")
    parser.add_argument(
        "--campaign",
        default="Summer23",
        choices=[
            "Summer22",
            "Summer22EE",
            "Summer23",
            "Summer23BPix",
            "Summer24",
            "CustomSummer24",
            "Prompt25",
            "2018-UL",
            "2017-UL",
            "2016preVFP-UL",
            "2016postVFP-UL",
            "CAMPAIGN_prompt_dataMC",
        ],
        help="Dataset campaign, change the corresponding correction files",
    )
    parser.add_argument(
        "--isSyst",
        default=False,
        type=str,
        choices=[
            "False",
            "all",
            "weight_only",
            "JEC_full",
            "JEC_reduced",
            "JEC_reduced_JER_split",
            "JEC_total",
            "JP_MC",
        ],
        help="Run with systematics (default: %(default)s)",
    )
    parser.add_argument(
        "--ttbar-reweights",
        default="none",
        choices=["none", "hdamp_ml", "full"],
        help=(
            "Enable additional ttbar event reweights in correction.py. "
            "'hdamp_ml' applies hdamp ONNX up/down; 'full' additionally reserves "
            "hooks for frag/decay reweights."
        ),
    )
    parser.add_argument("--isArray", action="store_true", help="Output root files")

    parser.add_argument(
        "--noHist", action="store_true", help="Not output coffea histogram"
    )
    parser.add_argument(
        "--overwrite", action="store_true", help="Overwrite existing files"
    )
    parser.add_argument(
        "--only",
        type=str,
        default=None,
        help="Only  process/skip part of the dataset. By input list of file",
    )
    parser.add_argument(
        "--voms",
        default=None,
        type=str,
        help="Path to voms proxy, made accessible to worker nodes. By default a copy will be made to $HOME.",
    )

    parser.add_argument(
        "--chunk",
        type=int,
        default=75000,
        metavar="N",
        help="Number of events per process chunk",
    )
    parser.add_argument("--skipbadfiles", action="store_true", help="Skip bad files.")
    parser.add_argument(
        "--dryrun",
        action="store_true",
        help="Prepare the tarball, job directory, and submit.jdl but do not actually call condor_submit",
    )
    parser = get_condor_submitter_parser(parser)
    return parser


if __name__ == "__main__":
    parser = get_main_parser()
    args = parser.parse_args()
    print("Running with the following options:")
    print(args)

    # execute.sh only transfers the .success marker back via HTCondor -- the
    # actual histograms/arrays are cp/xrdcp'd directly from the worker node
    # to outputDir. A relative (or otherwise non-shared) outputDir silently
    # writes into the worker's ephemeral scratch space and is lost for good.
    if not (args.outputDir.startswith("/") or args.outputDir.startswith("root://")):
        print(
            f"ERROR: --outputDir '{args.outputDir}' is not an absolute path or "
            "root:// URL. Jobs would write their output to worker-node-local "
            "scratch space and it would never reach you."
        )
        sys.exit(1)

    uid = os.getuid()
    homedir = os.getenv("HOME")
    expected_value = f"{homedir}/x509up_u{uid}"
    current_value = os.getenv("X509_USER_PROXY")
    if current_value != expected_value:
        print("X509_USER_PROXY is NOT set correctly.")
        print(f"Please run the following command in your shell:")
        print(f"export X509_USER_PROXY=$HOME/x509up_u`id -u`")
        sys.exit(1)

    current_dir = os.path.dirname(os.path.abspath(__file__))
    base_dir = current_dir.replace("/condor", "")

    if args.remoteRepo is not None:
        print("Will use a remote path to access BTVNanoCommissioning:", args.remoteRepo)
    else:
        print("Tarring BTVNanoCommissioning directory...")

        skip_tar = False
        if os.path.exists("BTVNanoCommissioning.tar.gz"):
            user_input = _prompt_yn(
                "BTVNanoCommissioning.tar.gz already exists, skip the tarring? ([y]/n): "
            )
            if user_input.lower() != "n":
                skip_tar = True
            else:
                skip_tar = False
                os.remove("BTVNanoCommissioning.tar.gz")

        if not skip_tar:
            jobdirs = [d for d in os.listdir(base_dir) if d.startswith("jobs_")]
            make_tarfile(
                "BTVNanoCommissioning.tar.gz",
                base_dir,
                # "metadata" (repo root and SFbc-2D/) holds dataset file-list
                # JSONs (100s of MB) that only fetch.py/submitter.py need --
                # each job gets its own file list via split_samples.json instead.
                # .git alone is ~666 MB; SFbc-2D/docs/notebooks/testfile are
                # analysis-side and never read by the job. Dropping these takes
                # the sandbox from 588 MB to ~38 MB per job.
                exclude_dirs=[
                    "BTVNanoCommissioning.egg-info",
                    "metadata",
                    ".git",
                    "SFbc-2D",
                    "docs",
                    "notebooks",
                    "testfile",
                    "__pycache__",
                ]
                + jobdirs,
            )

    # Create job dir
    job_dir = f"jobs_{args.jobName}"
    if os.path.exists(job_dir):
        user_input = _prompt_yn("Job directory already exists, overwrite? ([y]/n): ")
        if user_input.lower() != "n":
            shutil.rmtree(job_dir)
        else:
            raise Exception("Job exiting...")
    print(f"Job directory created: {job_dir}")
    os.mkdir(job_dir)
    os.mkdir(job_dir + "/log")

    # Store job submission files

    ## store parser arguments
    with open(os.path.join(job_dir, "arguments.json"), "w") as json_file:
        json.dump(vars(args), json_file, indent=4)

    ## split the sample json
    if isinstance(args.samplejson, str):
        samplejson = [args.samplejson]
    else:
        samplejson = args.samplejson
    sample_dict = {}
    for js in samplejson:
        with open(js) as f:
            sample_dict.update(json.load(f))

    split_sample_dict = {}
    counter = 0
    only = []
    if args.only is not None:
        if "*" in args.only:
            only = [
                k
                for k in sample_dict.keys()
                if k.lstrip("/").startswith(args.only.rstrip("*"))
            ]
        else:
            only.append(args.only)

    for sample_name, files in sample_dict.items():
        if len(only) != 0 and sample_name not in only:
            continue
        for ifile in range(
            (len(files) + args.condorFileSize - 1) // args.condorFileSize
        ):
            split_sample_dict[counter] = {
                sample_name: files[
                    ifile * args.condorFileSize : (ifile + 1) * args.condorFileSize
                ]
            }
            counter += 1

    ## store the split sample json file
    with open(os.path.join(job_dir, "split_samples.json"), "w") as json_file:
        json.dump(split_sample_dict, json_file, indent=4)
    ## store the jobnum list (0..jobnum-1)
    with open(os.path.join(job_dir, "jobnum_list.txt"), "w") as f:
        f.write("\n".join([str(i) for i in range(counter)]))

    ## store the jdl file
    max_retries = 10
    jdl_template = """Universe   = vanilla
Executable = {executable}


Arguments = $(JOBNUM) $(request_cpus)

request_cpus   = {nCPU}
request_memory = {request_memory}
use_x509userproxy = true

+JobFlavour = "{jobqueue}"
{accounting_group}

Log        = {log_dir}/job.log_$(Cluster)
Output     = {log_dir}/job.out_$(Cluster)-$(Process)
Error      = {log_dir}/job.err_$(Cluster)-$(Process)

max_retries             = {max_retries}
# Only release a held job (e.g. after a transient output-transfer failure) a
# bounded number of times, and not immediately -- otherwise a job stuck in a
# hold/release loop (for a reason max_retries can't see, since that only
# counts non-zero exits) retries forever instead of surfacing as held.
periodic_release        = (NumJobStarts < {max_retries}) && ((time() - EnteredCurrentStatus) > 600)
should_transfer_files   = YES
when_to_transfer_output = ON_EXIT_OR_EVICT
transfer_input_files    = {transfer_input_files}
JobBatchName            = {batch_name}
transfer_output_files   = .success

Queue JOBNUM from {jobnum_file}
""".format(
        executable=f"{base_dir}/condor/execute.sh",
        jobqueue=args.jobqueue,
        max_retries=max_retries,
        request_memory=f"{args.nCPU * 3}GB",
        accounting_group=(
            f'+AccountingGroup = "{args.accountingGroup}"'
            if args.accountingGroup
            else ""
        ),
        log_dir=f"{base_dir}/{job_dir}/log",
        transfer_input_files=f"{base_dir}/{job_dir}/arguments.json,{base_dir}/{job_dir}/split_samples.json,{base_dir}/{job_dir}/jobnum_list.txt"
        + ("" if args.remoteRepo else f",{base_dir}/BTVNanoCommissioning.tar.gz"),
        nCPU=args.nCPU,
        batch_name=args.jobName,
        jobnum_file=f"{base_dir}/{job_dir}/jobnum_list.txt",
    )
    with open(os.path.join(job_dir, "submit.jdl"), "w") as f:
        f.write(jdl_template)
    print(f"{counter} jobs prepared in {job_dir}/submit.jdl")
    if args.dryrun:
        print(
            f"Dry run: not submitting. To submit for real, run:\n  condor_submit {job_dir}/submit.jdl"
        )
    else:
        os.system(f"condor_submit {job_dir}/submit.jdl")
