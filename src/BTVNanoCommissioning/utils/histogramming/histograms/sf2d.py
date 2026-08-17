import numpy as np
import hist as Hist

# Jet pT grid for the 2D SF-fit templates. Settled by the phase4 category-
# scheme study (SFbc-2D/OptimizedWP): every flavour's pT tying is expressed
# as a group of these edges, so coarser groupings can be formed later by
# summing bins exactly. Do NOT add/move edges here.
_PT_EDGES = [25.0, 35.0, 50.0, 70.0, 90.0, 120.0, np.inf]

# The 2D category schemes to write a template for, as
# name -> (Jet branch holding the category code, category codes).
# Single source of truth: the fill sites import this rather than repeating the
# branch names, so a scheme is added here once.
#
# The two taggers share the same 4x8 mapping and therefore the same sparse
# 40s/50s code numbering; only the HFvLF/BvC cut values differ
# (utils/selection.py btag_wp_dict). phase4 is the re-optimised NoPIDParT
# scheme from SFbc-2D/OptimizedWP/results/phase4_scheme_NoPIDParT.json, which
# renumbers its 11 categories densely as 0..10. There is deliberately no
# phase4 entry for UParT: that optimisation was only ever run for NoPIDParT.
_LEGACY_CODES = [0, 40, 41, 42, 43, 44, 50, 51, 52, 53, 54]
SCHEMES = {
    "nopid_legacy": ("btagNoPIDParTAK42Dbin", _LEGACY_CODES),
    "nopid_phase4": ("btagNoPIDParTAK4_phase42Dbin", list(range(11))),
    "upart_legacy": ("btagUParTAK42Dbin", _LEGACY_CODES),
}


def get_histograms(axes, **kwargs):
    """SF-fit templates: tag category x jet pT x SV variable, for every scheme
    in SCHEMES and both SV-axis choices (nSVs, svmass). Filled in the
    DY/Wc/ttdilep 2D workflows.

    An svmass template is booked only for channels passing sf2d_svmass=True.
    The wrong-jet index that used to invalidate svmass outside DY was fixed in
    the framework (commit 111b17f), so all three template channels set it --
    but trees produced *before* that fix still carry the bad values, so this
    stays an explicit per-channel declaration rather than an unconditional
    booking.
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

    for scheme, (_branch, codes) in SCHEMES.items():
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
