import awkward as ak
import numpy as np
from coffea import processor
import os, gzip, importlib, cloudpickle
from coffea.jetmet_tools import JECStack, CorrectedJetsFactory, CorrectedMETFactory
from coffea.lookup_tools import extractor

import collections


from pathlib import Path


# Campaigns that aren't backed by their own CVMFS metadata directory and should
# instead resolve to another campaign's corrections (e.g. a private NanoAOD
# production reusing the same MiniAOD conditions as an official campaign).
_CAMPAIGN_ALIASES = {"CustomSummer24": "Summer24"}


def campaign_map():
    dirs = [
        Path("/cvmfs/cms-griddata.cern.ch/cat/metadata/JME/"),
        Path("/cvmfs/cms-griddata.cern.ch/cat/metadata/BTV/"),
        Path("/cvmfs/cms-griddata.cern.ch/cat/metadata/EGM/"),
        Path("/cvmfs/cms-griddata.cern.ch/cat/metadata/MUO/"),
        Path("/cvmfs/cms-griddata.cern.ch/cat/metadata/LUM/"),
    ]
    subdirs = [p.name for d in dirs if d.is_dir() for p in d.iterdir() if p.is_dir()]
    dirnames = {}
    for i in range(len(subdirs)):
        if "Run3" in subdirs[i]:
            if "25Prompt" in subdirs[i]:
                dirnames["Prompt25"] = subdirs[i]
            elif "26Prompt" in subdirs[i]:
                dirnames["Prompt26"] = subdirs[i]
            else:
                dirnames[subdirs[i].split("-")[2]] = subdirs[i]
        elif "Run2" in subdirs[i]:
            key = subdirs[i].split("-")[1] + "-UL"
            dirnames[key] = subdirs[i]
        elif "Run3" not in subdirs[i] and "Run2" not in subdirs[i]:
            continue
        else:
            raise ValueError("Unknown campaign name")
    for alias, target in _CAMPAIGN_ALIASES.items():
        if target in dirnames:
            dirnames[alias] = dirnames[target]
    return dirnames


def flatten(ar):  # flatten awkward into a 1d array to hist
    return ak.flatten(ar, axis=None)


def normalize(val, cut):
    if cut is None:
        ar = ak.to_numpy(ak.fill_none(val, np.nan))
        return ar
    else:
        ar = ak.to_numpy(ak.fill_none(val[cut], np.nan))
        return ar


def update(events, collections):
    """Return a shallow copy of events array with some collections swapped out"""
    out = events
    for name, value in collections.items():
        out = ak.with_field(out, value, name)
    return out


# return run & lumiblock in pairs
def dump_lumi(events, output):
    pairs = np.vstack((events.run.to_numpy(), events.luminosityBlock.to_numpy()))
    # remove replicas
    pairs = np.unique(np.transpose(pairs), axis=0)
    pairs = pairs[
        np.lexsort(([pairs[:, i] for i in range(pairs.shape[1] - 1, -1, -1)]))
    ]
    output["fname"] = processor.set_accumulator([events.metadata["filename"]])
    output["run"] = processor.column_accumulator(pairs[:, 0])
    output["lumi"] = processor.column_accumulator(pairs[:, 1])
    return output


## Based on https://github.com/CoffeaTeam/coffea/discussions/735
def _is_rootcompat(a):
    """Is it a flat or 1-d jagged array?"""
    t = ak.type(a)
    if isinstance(t, ak._ext.ArrayType):
        if isinstance(t.type, ak._ext.PrimitiveType):
            return True
        if isinstance(t.type, ak._ext.ListType) and isinstance(
            t.type.type, ak._ext.PrimitiveType
        ):
            return True
    return False


jec_name_map = {
    "JetPt": "pt",
    "JetPhi": "phi",
    "JetMass": "mass",
    "JetEta": "eta",
    "JetA": "area",
    "ptGenJet": "pt_gen",
    "ptRaw": "pt_raw",
    "massRaw": "mass_raw",
    "Rho": "event_rho",
    "METpt": "pt",
    "METphi": "phi",
    "JetPhi": "phi",
    "UnClusteredEnergyDeltaX": "MetUnclustEnUpDeltaX",
    "UnClusteredEnergyDeltaY": "MetUnclustEnUpDeltaY",
}


def _load_jmefactory(year, campaign, jme_compiles):
    _jet_path = f"BTVNanoCommissioning.data.JME.{campaign}"
    with importlib.resources.path(_jet_path, jme_compiles) as filename:
        with gzip.open(filename) as fin:
            jme_factory = cloudpickle.load(fin)
    return jme_factory


def __jet_factory_factory__(files):
    ext = extractor()
    ext.add_weight_sets([f"* * {file}" for file in files])
    ext.finalize()
    jec_stack = JECStack(ext.make_evaluator())
    return CorrectedJetsFactory(jec_name_map, jec_stack)


def _jet_factories_(campaign, factory_map):
    factory_info = {
        j: __jet_factory_factory__(files=factory_map[j]) for j in factory_map.keys()
    }
    return factory_info


def _compile_jec_(year, campaign, factory_map, name):
    # jme stuff not pickleable in coffea
    import cloudpickle

    # add postfix to txt files
    update_factory = {}
    directory_path = f"src/BTVNanoCommissioning/data/JME/{campaign}/"
    files_in_directory = os.listdir(directory_path)
    for t in factory_map:
        if t == "name":
            continue
        update_factory[t] = []
        for f in factory_map[t]:
            if "Resolution" in f:
                if not os.path.exists(
                    f"src/BTVNanoCommissioning/data/JME/{campaign}/{f}.jr.txt"
                ) and os.path.exists(
                    f"src/BTVNanoCommissioning/data/JME/{campaign}/{f}.txt"
                ):
                    os.system(
                        f"mv src/BTVNanoCommissioning/data/JME/{campaign}/{f}.txt src/BTVNanoCommissioning/data/JME/{campaign}/{f}.jr.txt"
                    )
                update_factory[t].append(
                    f"src/BTVNanoCommissioning/data/JME/{campaign}/{f}.jr.txt"
                )
            elif "SF" in f:
                if not os.path.exists(
                    f"src/BTVNanoCommissioning/data/JME/{campaign}/{f}.jersf.txt"
                ) and os.path.exists(
                    f"src/BTVNanoCommissioning/data/JME/{campaign}/{f}.txt"
                ):
                    os.system(
                        f"mv src/BTVNanoCommissioning/data/JME/{campaign}/{f}.txt src/BTVNanoCommissioning/data/JME/{campaign}/{f}.jersf.txt"
                    )
                update_factory[t].append(
                    f"src/BTVNanoCommissioning/data/JME/{campaign}/{f}.jersf.txt"
                )
            elif "Uncertainty" in f:
                if not os.path.exists(
                    f"src/BTVNanoCommissioning/data/JME/{campaign}/{f}.junc.txt"
                ) and os.path.exists(
                    f"src/BTVNanoCommissioning/data/JME/{campaign}/{f}.txt"
                ):
                    os.system(
                        f"mv src/BTVNanoCommissioning/data/JME/{campaign}/{f}.txt src/BTVNanoCommissioning/data/JME/{campaign}/{f}.junc.txt"
                    )
                update_factory[t].append(
                    f"src/BTVNanoCommissioning/data/JME/{campaign}/{f}.junc.txt"
                )
            else:
                if not os.path.exists(
                    f"src/BTVNanoCommissioning/data/JME/{campaign}/{f}.jec.txt"
                ) and os.path.exists(
                    f"src/BTVNanoCommissioning/data/JME/{campaign}/{f}.txt"
                ):
                    os.system(
                        f"mv src/BTVNanoCommissioning/data/JME/{campaign}/{f}.txt src/BTVNanoCommissioning/data/JME/{campaign}/{f}.jec.txt"
                    )
                update_factory[t].append(
                    f"src/BTVNanoCommissioning/data/JME/{campaign}/{f}.jec.txt"
                )

    with gzip.open(
        f"src/BTVNanoCommissioning/data/JME/{campaign}/{name}.pkl.gz", "wb"
    ) as fout:
        cloudpickle.dump(
            {
                "jet_factory": _jet_factories_(campaign, update_factory),
                "met_factory": CorrectedMETFactory(jec_name_map),
            },
            fout,
        )


def PFCand_link(events, event_level, jetindx):
    if str(ak.type(jetindx)).count("*") > 1:
        jetindx = jetindx[event_level]
        spfcands = collections.defaultdict(dict)
        for i in range(len(jetindx[0])):
            spfcands[i] = events[event_level].PFCands[
                events[event_level]
                .JetPFCands[events[event_level].JetPFCands.jetIdx == jetindx[:, i]]
                .pFCandsIdx
            ]

    else:
        spfcands = events[event_level].PFCands[
            events[event_level]
            .JetPFCands[events[event_level].JetPFCands.jetIdx == jetindx[event_level]]
            .pFCandsIdx
        ]
    return spfcands


def _local_pick(arr, idx, default):
    """Select arr[i][idx[i]] for each event i (idx may be a masked/padded
    per-event scalar index), filling `default` where idx is out of range."""
    mask = ak.local_index(arr) == idx[:, None]
    return ak.fill_none(ak.firsts(arr[mask]), default)


def SV_link_ragged(events, event_level, jetindx):
    """Attach the primary secondary vertex (Jet_svIdx1) to a ragged
    (variable jets/event) list of raw jet indices, e.g. a SelJet collection
    with a variable number of jets per event capped at some maximum. Unlike
    SV_link, this does not need a fixed per-event slot count and keeps the
    output jagged (no padding), matching the shape of `jetindx` itself.
    Jets with no matched SV (svIdx1 == -1) get -1.
    """
    jet = events[event_level].Jet
    sv = events[event_level].SV
    # pad SV collection with a dummy entry so index 0 is always valid, even
    # for events with zero SVs (ak.where evaluates both branches eagerly)
    nsv = ak.num(sv.mass, axis=1)
    sv_mass = ak.fill_none(ak.pad_none(sv.mass, 1, axis=1), -1.0)
    sv_dlensig = ak.fill_none(ak.pad_none(sv.dlenSig, 1, axis=1), -1.0)
    svidx1 = jet.svIdx1[jetindx]
    # Jet_svIdx1 can reference a secondary vertex that failed the SV
    # collection's own selection cuts and is therefore missing from `SV`
    # even though svIdx1 >= 0; guard against that out-of-range case too.
    has_sv = (svidx1 >= 0) & (svidx1 < nsv[:, None])
    safe_svidx = ak.where(has_sv, svidx1, 0)
    mass = ak.where(has_sv, sv_mass[safe_svidx], -1.0)
    dlensig = ak.where(has_sv, sv_dlensig[safe_svidx], -1.0)
    return mass, dlensig


def SV_link(events, event_level, jetindx):
    """Attach the primary secondary vertex (Jet_svIdx1, an index into the
    SV collection) to the given jet index/indices. Jets with no matched SV
    (svIdx1 == -1), or jet slots with no jet at all (padded jetindx), get -1.
    """
    jet = events[event_level].Jet
    sv = events[event_level].SV
    nsv = ak.num(sv.mass, axis=1)

    def sv_for(safe_jetidx, has_jet):
        svidx1 = _local_pick(jet.svIdx1, safe_jetidx, -1)
        # Jet_svIdx1 can reference a secondary vertex that failed the SV
        # collection's own selection cuts and is therefore missing from `SV`
        # even though svIdx1 >= 0; guard against that out-of-range case too.
        has_sv = has_jet & (svidx1 >= 0) & (svidx1 < nsv)
        safe_svidx = ak.where(has_sv, svidx1, 0)
        mass = ak.where(has_sv, _local_pick(sv.mass, safe_svidx, -1.0), -1.0)
        dlensig = ak.where(has_sv, _local_pick(sv.dlenSig, safe_svidx, -1.0), -1.0)
        return mass, dlensig

    if str(ak.type(jetindx)).count("*") > 1:
        jetindx = jetindx[event_level]
        svmass = collections.defaultdict(dict)
        svd3dsig = collections.defaultdict(dict)
        for i in range(len(jetindx[0])):
            idx = jetindx[:, i]
            has_jet = ~ak.is_none(idx)
            safe_jetidx = ak.fill_none(idx, 0)
            svmass[i], svd3dsig[i] = sv_for(safe_jetidx, has_jet)
    else:
        idx = jetindx[event_level]
        has_jet = ~ak.is_none(idx)
        safe_jetidx = ak.fill_none(idx, 0)
        svmass, svd3dsig = sv_for(safe_jetidx, has_jet)
    return svmass, svd3dsig


def uproot_writeable(events, include=["events", "run", "luminosityBlock"]):
    ev = {}
    include = np.array(include)
    no_filter = False
    if len(include) == 1 and include[0] == "*":
        no_filter = False
    for bname in events.fields:
        if not events[bname].fields:
            if not no_filter and bname not in include:
                continue
            ev[bname] = ak.fill_none(
                ak.packed(ak.without_parameters(events[bname])), -99
            )
        else:
            b_nest = {}
            no_filter_nest = False
            if all(np.char.startswith(include, bname) == False):
                continue
            include_nest = [
                i[i.find(bname) + len(bname) + 1 :]
                for i in include
                if i.startswith(bname)
            ]

            if len(include_nest) == 1 and include_nest[0] == "*":
                no_filter_nest = True

            if not no_filter_nest:
                mask_wildcard = np.char.find(include_nest, "*") != -1
                include_nest = np.char.replace(include_nest, "*", "")
            for n in events[bname].fields:
                ## make selections to the filter case, keep cross-ref ("Idx")
                if (
                    not no_filter_nest
                    and all(np.char.find(n, include_nest) == -1)
                    and "Idx" not in n
                    and "Flavor" not in n
                ):
                    continue
                evnums = ak.num(events[bname][n], axis=0)
                if not isinstance(evnums, int):
                    continue
                if not _is_rootcompat(events[bname][n]) and evnums != len(
                    flatten(events[bname][n])
                ):
                    continue
                # skip IdxG
                if "IdxG" in n:
                    continue
                b_nest[n] = ak.fill_none(
                    ak.packed(ak.without_parameters(events[bname][n])), -99
                )
            if bool(b_nest):
                ev[bname] = ak.zip(b_nest)
    return ev
