import argparse, glob, os
import numpy as np
import awkward as ak
import uproot

# Central weight components array_writer() (utils/array_writer.py) writes per event.
# Their product reconstructs the full nominal Weights().weight() used for histogramming.
WEIGHT_BRANCHES = ["genWeight", "ttbar_weight", "puwei", "muWeight", "eleWeight", "ftagWeight"]

# Integrated luminosity per campaign, in /pb. Kept in sync with SFbc-2D/05_make_templates.sh.
LUMI_PB = {
    "Summer22": 7980,
    "Summer22EE": 26700,
    "Summer23": 18100,
    "Summer23BPix": 9690,
    "Summer24": 110000,
    "Prompt25": 110000,
    "CustomSummer24": 110000,  # private NanoAODv15 production, uses Summer24 corrections/lumi
}

parser = argparse.ArgumentParser(
    description="Add `lumi` (the integrated luminosity, in pb, used for this normalization) and "
    "`weight` (xsec * lumi / sumw, times the SF weight components already written per event) "
    "branches to hadd'd array-output root files produced by array_writer() (see "
    "condor_lxplus/haddoutputs.py for the hadd step). All existing branches, including the "
    "individual xSecWeight/genWeight/puwei/ftagWeight/ttbar_weight/muWeight/eleWeight "
    "components `weight` is built from, are kept as-is."
)
parser.add_argument("input_dir", help="Directory of hadd'd files, e.g. <outputDir>/hadd")
parser.add_argument(
    "output_dir", help="Where to write the normalized files, e.g. <outputDir>/hadd_normalized"
)
lumi_group = parser.add_mutually_exclusive_group(required=True)
lumi_group.add_argument(
    "--campaign", choices=sorted(LUMI_PB), help="Look up the integrated luminosity for this campaign"
)
lumi_group.add_argument("--lumi", type=float, help="Integrated luminosity in /pb")
parser.add_argument(
    "--dry-run", action="store_true", help="Print what would be done, don't write anything"
)


def normalize_file(in_file, out_file, lumi_pb, dry_run):
    with uproot.open(in_file) as f:
        is_mc = "TotalEventWeight" in f
        n_total = float(np.sum(f["TotalEventCount"]["TotalEventCount"].array(library="np")))
        sumw = (
            float(np.sum(f["TotalEventWeight"]["TotalEventWeight"].array(library="np")))
            if is_mc
            else None
        )
        if "Events" not in f or f["Events"].num_entries == 0:
            print(f"WARNING: no selected events in {in_file}, skipping")
            return
        events = f["Events"].arrays(library="ak")

    if is_mc:
        if sumw == 0:
            raise ValueError(f"sumw is 0 for {in_file}, cannot normalize")
        weight = events["xSecWeight"] * (lumi_pb / sumw)
        for branch in WEIGHT_BRANCHES:
            weight = weight * events[branch]
    else:
        weight = ak.Array(np.ones(len(events)))

    print(
        f"{in_file}: {'MC' if is_mc else 'data'}, n_processed={n_total:.0f}"
        + (f", sumw={sumw:.6g}, lumi={lumi_pb:.6g}/pb" if is_mc else "")
    )
    if dry_run:
        return

    events["lumi"] = ak.Array(np.full(len(events), lumi_pb))
    events["weight"] = weight
    os.makedirs(os.path.dirname(out_file), exist_ok=True)
    with uproot.recreate(out_file) as fout:
        fout["Events"] = events
        fout["TotalEventCount"] = ak.Array({"TotalEventCount": [n_total]})
        if is_mc:
            fout["TotalEventWeight"] = ak.Array({"TotalEventWeight": [sumw]})


if __name__ == "__main__":
    args = parser.parse_args()
    lumi_pb = LUMI_PB[args.campaign] if args.campaign else args.lumi

    files = glob.glob(f"{args.input_dir}/*/*.root")
    if len(files) == 0:
        print(f"Found zero .root files in {args.input_dir}/*/*.root -- are you pointing at a `hadd` directory?")
        exit()

    for in_file in files:
        rel = os.path.relpath(in_file, args.input_dir)
        out_file = f"{args.output_dir}/{rel}"
        normalize_file(in_file, out_file, lumi_pb, args.dry_run)
