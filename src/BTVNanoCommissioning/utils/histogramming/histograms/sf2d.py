import numpy as np
import hist as Hist

# Jet pT grid for the 2D SF-fit templates. Settled by the phase4 category-
# scheme study (SFbc-2D/OptimizedWP): every flavour's pT tying is expressed
# as a group of these edges, so coarser groupings can be formed later by
# summing bins exactly. Do NOT add/move edges here.
_PT_EDGES = [25.0, 35.0, 50.0, 70.0, 90.0, 120.0, np.inf]

# Tag-category codes for each 2D scheme (utils/selection.py btag_wp_dict):
# legacy is the sparse 40s/50s numbering, phase4 is the dense 0..10 scheme
# from SFbc-2D/OptimizedWP/results/phase4_scheme_NoPIDParT.json.
_SCHEMES = {
    "legacy": [0, 40, 41, 42, 43, 44, 50, 51, 52, 53, 54],
    "phase4": list(range(11)),
}


def get_histograms(axes, **kwargs):
    """SF-fit templates: tag category x jet pT x SV variable, for both the
    legacy and phase4 2D category schemes, and for both SV-axis choices
    (SelJet_nSVs, SelJet_svmass). Filled in the DY/Wc/ttdilep 2D workflows.

    The svmass template is only booked for channels that pass
    sf2d_svmass=True, which today means DY alone: a wrong-jet index
    invalidates SelJet_svmass in W+c and ttdilep in the current trees (see
    SFbc-2D/OptimizedWP/CLAUDE.md). The workflow is what knows whether the
    branch is trustworthy, so it declares it here -- the fill code must not
    have to guess from the event content.
    """
    include_osss = kwargs.get("include_osss", False)
    include_svmass = kwargs.get("sf2d_svmass", False)

    hists = {}

    pt_axis = Hist.axis.Variable(_PT_EDGES, name="pt", label=" $p_{T}$ [GeV]")
    nsv_axis = Hist.axis.Integer(
        0, 5, name="nSVs", label="N secondary vertices", overflow=True
    )
    svmass_axis = Hist.axis.Regular(
        100, 0.0, 10.0, name="svmass", label="SV mass [GeV]"
    )

    common_axes = [axes["syst"], axes["flav"]]
    if include_osss:
        common_axes.append(axes["osss"])

    for scheme, codes in _SCHEMES.items():
        tagcat_axis = Hist.axis.IntCategory(
            codes, name="tagcat", label=f"tag category ({scheme})"
        )

        hists[f"sf2d_{scheme}_nSVs"] = Hist.Hist(
            *common_axes, tagcat_axis, pt_axis, nsv_axis, Hist.storage.Weight()
        )
        if include_svmass:
            hists[f"sf2d_{scheme}_svmass"] = Hist.Hist(
                *common_axes, tagcat_axis, pt_axis, svmass_axis, Hist.storage.Weight()
            )

    return hists
