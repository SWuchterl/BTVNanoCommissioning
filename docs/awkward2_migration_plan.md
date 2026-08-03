# Awkward2 / Coffea Migration — Plan

Plan only. No changes made. Written 2026-08-03.

Supersedes the scoping in `docs/awkward2_architecture_review.md`, `docs/awkward2_refactor_review.md`
and `docs/awkward2_simplify_review.md` where they disagree — see "Corrections to the reviews" below.
Feeds the "Strategic note: the coffea pin" item at the bottom of `docs/modernization_plan.md`.

Baseline: `coffea==0.7.31`, `awkward 1.10.5`, `uproot 4.3.7`, `correctionlib==2.7.0`,
`numpy 1.26.4`, `numba 0.66.0`, Python 3.10.

Target: **coffea's eager `Runner` + `ProcessorABC` model.** Explicitly *not* the dask-awkward
rewrite — that touches every workflow's event-level code and contradicts "avoid large rewrites".

---

## Decisions taken

| # | Decision | Rationale |
|---|---|---|
| 1 | Delete the unused executors rather than port them | Nothing in this repo or `autobtv` invokes parsl / `dask/casa` / `condor_standalone`. Pending a final check with the team. |
| 2 | Drop `Rereco17_94X` and `Winter22` campaigns | They are the only consumers of the cloudpickled coffea-0.7 JEC factories, which cannot survive the bump. |
| 3 | Cutover tolerance: exact on counts, `rtol=1e-9` on weights | Catches any real logic change while tolerating float reassociation from the numpy/backend bump. Fixed *before* seeing diffs, deliberately. |
| 4 | Target eager `Runner`, not dask-awkward | Keeps `process()`/`process_shift()` in all 19 workflows untouched. |

---

## Corrections to the three review documents

**1. The executor rewrite was scoped far too high (L-XL → M).** The architecture review calls
`runner.py:626-1150` the largest coupling surface and treats the parsl migration as a site-support
question. But no caller uses those paths:

```
--executor iterative   23x   (CI, condor/execute.sh, condor_lxplus/execute.sh)
--executor futures      5x   (condor/execute.sh:115, condor_lxplus/execute.sh:50)
--executor parsl/*      0x
--executor dask/*       0x
```

`autobtv` was checked directly (2026-08-03): all three `runner.py` invocations in its
`.gitlab-ci.yml` (`:225`, `:577`, `:588`) use `--executor futures`. parsl and dask are *installed*
in its image (`Dockerfile:54`, `environment.yml`) but never invoked — which is probably why these
executors looked load-bearing. The correct action is deletion, not a port.

Note: `docs/modernization_plan.md` item 7 states that `2D_*_Wc_sf` run via `condor_standalone` in
production. That contradicts `condor_lxplus/execute.sh`, which uses `futures`. Resolve before
deleting.

**2. The reviews missed the cloudpickled JEC factories.** `data/JME/*/jec_compiled*.pkl.gz`
(6 files) hold serialized coffea-0.7 `CorrectedJetsFactory`/`JECStack` objects with awkward1-era
lookups inside. They will not unpickle after the bump, and `helpers/func.py:128`
(`JECStack(ext.make_evaluator())`) has a changed constructor signature in modern coffea. Bounded,
though: only `Rereco17_94X` (`AK4_parameters.py:6`) and `Winter22` (`:174`) use that path.
Everything Summer22 onward goes through correctionlib JME tags, which are coffea-independent.

**3. The environment has already drifted past its pin.** Installed `dask 2026.6.0` against
`coffea==0.7.31`; `test_env.yml` pins nothing on dask. Python 3.10 is EOL in October 2026. The
reviews assessed `test_env.yml`, not the live environment. This is not an argument for a larger
migration — it is an argument that "do nothing" is not a stable state.

**4. Harness coverage gap.** `scripts/phase0_regression.sh` covers only `2D_mu_Wc_sf` and
`2D_emu_ttdilep_sf`. Neither exercises `BTA_producer`, the sole consumer of `cumsum()` /
`calc_ip_vector()`. The most physics-sensitive function in the migration has no regression
coverage today.

**5. Unmentioned smaller items.** `processor.column_accumulator` (2 sites),
`processor.set_accumulator` (1 site); `condor/execute.sh:63` hardcodes
`micromamba install python=3.10`.

**What the reviews got right:** histogramming is genuinely already on modern `hist` (only a stale
comment at `plot_utils.py:271`); `BTA_helper.py:147-156` is the one confirmed hard rewrite and the
repo's only `ak.layout` use; the Phase 0 harness is the right validation tool and needs extending,
not rebuilding.

---

## Sequencing principle

Two independent tracks.

**Track A** is worth doing whether or not the migration happens. It is validated in the *current*
environment, where the baseline is trustworthy, and it shrinks the migration surface before the
bump starts.

**Track B** is the version bump.

Do not interleave them. If a rewrite and the bump land together, a diff cannot be attributed to
either.

---

## Track A — current environment

### A0. Close the harness gap *(prerequisite for everything else)*

- Add `BTA_producer` to `phase0_regression.sh` → verify: a repeat run diffs clean against itself.
- Encode the tolerance in `compare_coffea.py`: exact on event counts, selection masks and jagged
  structure; `rtol=1e-9` on weights and bin contents.
- Regenerate the baseline; stamp `pip freeze` alongside the commit hash (the live env has drifted
  from `test_env.yml`).

Benefit: every later verification depends on it. Complexity: low. Risk: none.
Files: `scripts/phase0_regression.sh`, `scripts/compare_coffea.py`.

### A1. Drop `Rereco17_94X` and `Winter22`

Removes more than the pickles:

| Removed | Why |
|---|---|
| `coffea.jetmet_tools` (`JECStack`, `CorrectedJetsFactory`, `CorrectedMETFactory`) | `func.py:5` — only these two campaigns use `jec_compiled*.pkl.gz` |
| `coffea.btag_tools.BTagScaleFactor` | `correction.py:24,182,193` — `Rereco17_94X` is the only campaign with `.csv` b-tag SFs (`AK4_parameters.py:8-11`) |
| `_load_jmefactory`, `__jet_factory_factory__`, `_jet_factories_`, `_compile_jec_`, `jec_name_map` | dead once no campaign loads a pickle |
| 6x `jec_compiled*.pkl.gz`, `94XPUwei_corrections.pkl.gz` | the coffea-0.7 cloudpickles |
| legacy branches at `correction.py:661`, `:2102`, and the `else` arms of `:2509`/`:2546` | dual-path collapse |

**Does not go:** `coffea.lookup_tools.{extractor, dense_lookup}` stays — the UL16/17/18 campaigns
being kept use `.histo.root` through it, and the EGM/MUO/JMAR dual paths at `:2609`, `:2842`,
`:3014`, `:3091` serve those. Do not let this step grow into removing them.

Constraints:
- Preserve the `$PROMPT_DATAMC` placeholder text in `AK4_parameters.py` — `autobtv` `sed`s against
  it (`.gitlab-ci.yml:177`).
- Confirm on the BTV list that nobody still runs these campaigns before deleting data files.

Verify: Phase 0 clean on Summer24 (untouched campaigns), plus a grep sweep for orphaned references.

Benefit: eliminates the hardest migration blocker; drops two coffea subpackages outright.
Complexity: medium (mechanical but wide). Risk: low-medium, fully revertible.
Files: `utils/AK4_parameters.py`, `utils/correction.py`, `helpers/func.py`, `data/JME/*`,
`data/LUM/Rereco17_94X/`.

### A2. Rewrite `cumsum()` awkward-1/2-portable

`BTA_helper.py:147-156` is the repo's only `ak.layout` use. Replace the layout surgery with
flatten → `np.cumsum` → re-offset → `ak.unflatten`, valid under both awkward versions.

Verify: bit-identical `ak.to_numpy` comparison against current output on the BTA fileset — not an
eyeball review — plus a clean A0 BTA ROOT diff.

Benefit: removes the one confirmed hard rewrite from the migration, validated where the reference
is trustworthy. Complexity: low. Risk: medium (feeds impact-parameter output consumed by
`SFbc-2D`), bounded by A0 coverage. Files: `helpers/BTA_helper.py`.

### A3. Delete unused executors *(gated on the team check)*

`runner.py:785-1150` — parsl, `dask/casa`, `condor_standalone` — plus `parsl` and `dask-jobqueue`
from `test_env.yml`. Slot in whenever the dask/parsl question is settled; nothing else blocks on it.

Benefit: ~500 lines deleted; roughly halves the Track B executor port. Complexity: low (deletion).
Risk: low once confirmed. Files: `runner.py`, `test_env.yml`, `CLAUDE.md`, `docs/scaleout.md`.

---

## Track B — the bump

### B1. Timeboxed spike — 5 days, hard stop, throwaway branch

Parallel env: `coffea 2025.x`, `awkward>=2`, `uproot>=5`, `numpy>=2`, matched `numba`,
Python 3.11+. Port `example.py` and the `iterative`/`futures` path only. Answer with evidence:

1. Does eager `processor.Runner` still exist and accept a `ProcessorABC`? **If no, the whole
   approach is re-evaluated.** First question, not an assumption.
2. Does `PFNanoAODSchema` still tolerate `update_branch.py`'s `missing_branch` backfill on the
   custom NanoAOD?
3. Do all four `with_name` classes still resolve via `coffea.nanoevents.methods.vector`?
   `PtEtaPhiMLorentzVector` (12 sites), `FourVector` (5), `ThreeVector` (3),
   `PtEtaPhiECandidate` (1).
4. Signature check: `lookup_tools.{extractor, txt_converters, rochester_lookup}`, `dense_lookup`,
   `lumi_tools.LumiMask`, `analysis_tools.Weights`.
5. `processor.column_accumulator` (2), `set_accumulator` (1), `accumulate` (19) still present?

Deliverable: a go/no-go and a day count. **Nothing merges.**

### B2. Migration branch

Executor port → `correction.py` per-import verification pass → `setup.cfg` / `test_env.yml` /
`condor*/execute.sh` Python bump (`condor/execute.sh:63` hardcodes `python=3.10`) → CI matrix.
Sequenced so each step is individually revertible.

### B3. Cutover

Old-env vs new-env Phase 0 diff on **identical input files**, per workflow, both `.coffea` and
`--isArray` ROOT. Decision 3's tolerance is the pass criterion. Then run one real production batch
in parallel under both environments before the pin on `master` moves.

---

## Estimate

Track A: ~4-5 days, stands alone.
Track B: ~2 weeks after a clean spike.

The honest uncertainty is concentrated in B1 question 1 — everything downstream assumes the answer
is yes.

---

## Out of scope / deferred

- **`autobtv`.** Checked once (see corrections above) and parked. Two items to revisit before
  cutover: its image builds from the fork `github.com/ValVau/BTVNanoCommissioning.git`
  (`Dockerfile:49`) using this repo's `test_env.yml`, so the pin propagates *through that fork* —
  the migration is not done until it is synced or the Dockerfile repointed. And its inline merge
  block (`.gitlab-ci.yml:788-793`) uses `coffea.util.load/save` and `coffea.processor.accumulate`;
  both are expected to survive, and are on the B1 checklist.
- **`gitlab.cern.ch/cms-btv/btv-sf-code`.** Not checked — subprojects could not be enumerated
  without API access. If those repos consume `.coffea`/ROOT *outputs* they are covered by B3; if
  any import this package's modules, that is a second compatibility obligation not costed here.
- **CLI surface contract.** `autobtv` depends on `--wf --json --year --campaign --executor
  --workers --chunk --retries --outputdir --limit`, plus `scripts/fetch.py` and
  `scripts/plotdataMC.py`. Nothing in this plan changes them; keep it that way.
