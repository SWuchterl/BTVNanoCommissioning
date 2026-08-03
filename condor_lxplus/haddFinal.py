import argparse, os
from glob import glob

parser = argparse.ArgumentParser(
    description="Merge per-dataset normalized array-output root files (see "
    "condor_lxplus/normalizeArrays.py) into one combined MC.root and one combined data.root "
    "per systematic. This is safe to do at this stage -- but not before normalizeArrays.py -- "
    "because every event already carries its final self-normalized `weight` branch "
    "(xsec * lumi / sumw, times the SF weight components), so merging trees across datasets "
    "no longer needs any dataset-specific bookkeeping (xSecWeight/sumw)."
)
parser.add_argument("output_dir", help="Where to write <output_dir>/<syst>/{MC,data}.root")
parser.add_argument(
    "--mc", nargs="+", required=True, metavar="DIR",
    help="One or more hadd_normalized directories to merge into MC.root, e.g. the MC and "
    "minor_MC job outputs' hadd_normalized directories",
)
parser.add_argument(
    "--data", nargs="+", required=True, metavar="DIR",
    help="One or more hadd_normalized directories to merge into data.root",
)
parser.add_argument(
    "-f", "--force", action="store_true",
    help="overwrite existing merged files instead of leaving them untouched (hadd's default)",
)
args = parser.parse_args()

systlist = sorted(
    set(os.path.basename(s) for d in (args.mc + args.data) for s in glob(f"{d}/*"))
)

if len(systlist) == 0:
    print("Found zero systematics under the given directories -- are you pointing at hadd_normalized dirs?")
    exit()

cmdlist = []
for syst in systlist:
    newoutdir = f"{args.output_dir}/{syst}"
    os.makedirs(newoutdir, exist_ok=True)

    mc_files = [f for d in args.mc for f in glob(f"{d}/{syst}/*.root")]
    data_files = [f for d in args.data for f in glob(f"{d}/{syst}/*.root")]

    if mc_files:
        cmdlist.append(
            f"hadd -v 0 -k {'-f ' if args.force else ''}{newoutdir}/MC.root "
            + " ".join(mc_files)
        )
    if data_files:
        cmdlist.append(
            f"hadd -v 0 -k {'-f ' if args.force else ''}{newoutdir}/data.root "
            + " ".join(data_files)
        )

if len(cmdlist) == 0:
    print("Found zero files to hadd. Are you pointing to the right directories?")
    exit()

haddfile = f"{args.output_dir}/dohadd_final.sh"
print()
with open(haddfile, "w") as outfl:
    for cmd in cmdlist:
        outfl.write(cmd + "\n")
        print(cmd)

print("\nNow switch to a root env and run:")
print("bash", haddfile)
print("or")
print(f"parallel :::: {haddfile}")
