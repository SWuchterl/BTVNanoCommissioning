# Awkward2 / Coffea Migration — Plan

Plan only. No changes made. Written 2026-08-03, revised same day after direct API verification
against the `coffea 2026.7.0` wheel.

Supersedes the scoping in `docs/awkward2_architecture_review.md`, `docs/awkward2_refactor_review.md`
and `docs/awkward2_simplify_review.md` where they disagree — see "Corrections to the reviews".
Feeds the "Strategic note: the coffea pin" item at the bottom of `docs/modernization_plan.md`.

Baseline: `coffea==0.7.31`, `awkward 1.10.5`, `uproot 4.3.7`, `correctionlib==2.7.0`,
`numpy 1.26.4`, `numba 0.66.0`, `parsl 2024.01.29`, `dask_jobqueue 0.9.0`, Python 3.10.

Target: **`coffea 2026.7.0`, eager `Runner` + `ProcessorABC`.** Not the dask-awkward rewrite —
that touches every workflow's event-level code and contradicts "avoid large rewrites".

---

## Headline: this is much smaller than the reviews implied

Two verified facts reshape the whole plan.

**1. `processor.Runner` and the executor *classes* already exist in coffea 0.7.31.**

```
coffea 0.7.31 exposes: DaskExecutor, FuturesExecutor, IterativeExecutor, ParslExecutor,
                       Runner, TaskVineExecutor, WorkQueueExecutor
                       (plus the deprecated *_executor functions currently used)
```

So the `run_uproot_job` → `Runner` port — the single largest piece of work in the reviews' scoping —
**can be done today, in the current environment, validated bit-for-bit against the Phase 0
baseline.** It does not need the version bump, and it does not need a spike. This moves the biggest
item from Track B to Track A, where the reference output is trustworthy.

**2. Every coffea API this repo uses survives in 2026.7.0, including parsl.**

`run_uproot_job` is the *only* removal. The architecture review's claim that modern coffea "dropped
parsl support entirely" is wrong.

---

## Verified compatibility matrix

Checked by unpacking the `coffea-2026.7.0-py3-none-any.whl` and by introspecting the installed
0.7.31. Not inferred.

| Repo dependency | Status in coffea 2026.7.0 |
|---|---|
| `processor.Runner`, `ProcessorABC` | present |
| `IterativeExecutor`, `FuturesExecutor`, `DaskExecutor`, `ParslExecutor`, `TaskVineExecutor` | all present and exported in `__all__` |
| `processor.run_uproot_job` | **removed** — the only one |
| `processor.accumulate`, `column_accumulator`, `set_accumulator` | present |
| `nanoevents.NanoAODSchema`, `PFNanoAODSchema` | present |
| `nanoevents.methods.vector` — `ThreeVector`, `PtEtaPhiMLorentzVector` | present, registered via `@awkward.mixin_class(behavior)`; the module docstring shows this repo's exact `with_name=`/`behavior=` idiom |
| `nanoevents.methods.candidate.PtEtaPhiECandidate` | present |
| `lookup_tools` — `extractor`, `txt_converters`, `rochester_lookup`, `dense_lookup` | all present |
| `lumi_tools.LumiMask`, `analysis_tools.Weights`, `util.load/save` | present |
| `btag_tools.BTagScaleFactor` | present |
| `jetmet_tools` — `JECStack`, `CorrectedJetsFactory`, `CorrectedMETFactory` | present |

**Dependency floors** (`METADATA`): `Requires-Python >=3.10`, `awkward>=2.8.11`, `uproot>=5.7.0`,
`numpy>=1.22`, `numba>=0.58.1`, `correctionlib>=2.6.0`, `hist>=2`; `parsl>=2024.12.09` and
`dask` as extras.

Two consequences worth stating plainly:

- **No forced Python bump.** 3.10 satisfies the floor. (Bumping anyway is still wise — 3.10 is EOL
  October 2026 — but it is decoupled from this migration.)
- **No forced numpy 2 bump.** `numpy>=1.22` means the current 1.26.4 is fine. Most of the
  float-reassociation risk behind decision 3's tolerance comes from a numpy major bump; holding
  numpy still during the migration should make results far closer to bit-identical, and isolates
  any diff to awkward/uproot.

---

## The real remaining work is parsl's API, not coffea's

`runner.py:782` imports `from parsl.channels import LocalChannel`, used at 4 sites feeding 9
`HighThroughputExecutor` blocks (7 `CondorProvider`, 4 `SlurmProvider`, 1 `LocalProvider`,
4 `SrunLauncher`).

**parsl removed Channels.** The installed `parsl 2024.01.29` still has them; coffea 2026.7.0
requires `parsl>=2024.12.09`, which is past the removal. So every `channel=LocalChannel(script_dir=...)`
argument must go, and `script_dir` moves to the provider.

This is now the largest single code change in the migration — and it is a *parsl* change that would
have been required by any parsl upgrade, migration or not. It is mechanical and repetitive rather
than subtle, and it touches no physics.

Same shape, smaller: `condor_standalone` uses `dask_jobqueue 0.9.0` `HTCondorCluster` /
`lpcjobqueue.LPCCondorCluster`. Needs an API-drift check against current `dask_jobqueue`, but
`distributed 2026.6.0` is already installed alongside coffea 0.7.31, so the cluster side is
partially exercised today.

---

## Decisions taken

| # | Decision | Rationale |
|---|---|---|
| 1 | **Keep parsl, dask and classic HTCondor executors.** *(revised 2026-08-03)* | Different users run different clusters and need them. Verified: all still supported in coffea 2026.7.0. Supersedes the earlier "delete" decision. |
| 2 | Drop `Rereco17_94X` and `Winter22` campaigns | The cloudpickled coffea-0.7 JEC factories cannot be unpickled after the bump. Note the *classes* survive — see below. |
| 3 | Cutover tolerance: exact on counts, `rtol=1e-9` on weights | Fixed before seeing diffs, deliberately. Holding numpy still should make this comfortable. |
| 4 | Target eager `Runner`, not dask-awkward | Keeps `process()`/`process_shift()` in all 19 workflows untouched. |

On decision 2, the justification is narrower than first written: `jetmet_tools` and `btag_tools`
both survive in 2026.7.0, so this is **not** forced by API removal. It is forced by the
*serialized payloads* — `data/JME/*/jec_compiled*.pkl.gz` (6 files) and
`data/LUM/Rereco17_94X/94XPUwei_corrections.pkl.gz` hold coffea-0.7 objects with awkward1 lookups
inside, which will not survive. The alternative is regenerating them via `_compile_jec_` under the
new environment and re-validating Run 2 JEC output against a reference that may no longer exist.
Dropping remains the recommendation, but it is now a cost/benefit call rather than a blocker.

---

## Corrections to the three review documents

**1. "Modern coffea dropped parsl support entirely" — false.** `ParslExecutor` is present and
exported in coffea 2026.7.0. The parsl work is real but it is parsl's own Channels removal, not a
coffea successor-hunt.

**2. The executor layer was scoped L-XL; it is M, and most of it belongs in Track A.** `Runner` and
the executor classes exist in 0.7.31, so the port is a same-environment refactor with a trustworthy
baseline, not a post-bump rewrite.

**3. The reviews missed the cloudpickled JEC factories** (`data/JME/*/jec_compiled*.pkl.gz`,
`func.py:128`). See decision 2.

**4. The environment has already drifted past its pin.** `dask 2026.6.0` / `distributed 2026.6.0`
against `coffea==0.7.31`; `test_env.yml` pins neither. Python 3.10 is EOL October 2026. "Do
nothing" is not a stable state.

**5. Harness coverage gap.** `scripts/phase0_regression.sh` covers only `2D_mu_Wc_sf` and
`2D_emu_ttdilep_sf`. Neither exercises `BTA_producer`, the sole consumer of `cumsum()` /
`calc_ip_vector()` — the most physics-sensitive function in the migration has no regression
coverage today.

**6. `with_name="FourVector"` is not a registered behavior name — in either version.** The
registered names in 0.7.31 are `TwoVector`, `PolarTwoVector`, `ThreeVector`, `SphericalThreeVector`,
`LorentzVector`, `PtEtaPhiMLorentzVector`, `PtEtaPhiELorentzVector`. All 5 `FourVector` sites are in
`workflows/sf_ttsemilep_tnp.py` and operate on raw `.x/.y/.z/.t` fields through local helpers
(`_four_mass`, `_four_pt`), so no coffea behavior was ever attached. The label is cosmetic and
carries **zero** migration risk. Not a bug — just not the risk the review flagged.

**What the reviews got right:** histogramming is genuinely already on modern `hist`;
`BTA_helper.py:147-156` is the one confirmed hard rewrite and the repo's only `ak.layout` use; the
Phase 0 harness is the right validation tool and needs extending, not rebuilding.

---

## Sequencing principle

Two tracks. **Track A** runs entirely in the *current* environment, where the Phase 0 baseline is
trustworthy, and now absorbs the executor port. **Track B** is the version bump alone.

Do not interleave. If a refactor and the bump land together, a diff cannot be attributed to either.

---

## Track A — current environment, coffea 0.7.31

### A0. Close the harness gap *(prerequisite for everything else)*

- Add `BTA_producer` to `phase0_regression.sh` → verify: a repeat run diffs clean against itself.
- Encode the tolerance in `compare_coffea.py`: exact on event counts, selection masks and jagged
  structure; `rtol=1e-9` on weights and bin contents.
- Regenerate the baseline; stamp `pip freeze` alongside the commit hash.

Benefit: every later verification depends on it. Complexity: low. Risk: none.
Files: `scripts/phase0_regression.sh`, `scripts/compare_coffea.py`.

### A1. Port `run_uproot_job` → `Runner`, in coffea 0.7.31

Replace the 5 `run_uproot_job` call sites and the 4 function-style executors
(`iterative_executor`, `futures_executor`, `parsl_executor`, `dask_executor`) with `Runner` plus
`IterativeExecutor`/`FuturesExecutor`/`ParslExecutor`/`DaskExecutor`. All exist in 0.7.31.

This is the migration's biggest item, done where it can be verified. After it, the only
coffea-version-sensitive thing left in `runner.py` is the parsl config itself.

→ verify: Phase 0 clean for every executor path that can be exercised locally
(`iterative`, `futures`); a smoke submission for each cluster path that cannot.

Benefit: removes the only *removed* coffea API from the codebase, ahead of the bump.
Complexity: medium. Risk: medium — orchestration, not event math, and fully covered by A0.
Files: `runner.py`.

### A2. Drop `Rereco17_94X` and `Winter22`

| Removed | Why |
|---|---|
| `coffea.jetmet_tools` import (`func.py:5`) | only these two campaigns use `jec_compiled*.pkl.gz` |
| `coffea.btag_tools.BTagScaleFactor` (`correction.py:24,182,193`) | `Rereco17_94X` is the only campaign with `.csv` b-tag SFs (`AK4_parameters.py:8-11`) |
| `_load_jmefactory`, `__jet_factory_factory__`, `_jet_factories_`, `_compile_jec_`, `jec_name_map` | dead once no campaign loads a pickle |
| 6x `jec_compiled*.pkl.gz`, `94XPUwei_corrections.pkl.gz` | the coffea-0.7 cloudpickles |
| legacy branches at `correction.py:661`, `:2102`, and the `else` arms of `:2509`/`:2546` | dual-path collapse |

**Does not go:** `coffea.lookup_tools.{extractor, dense_lookup}` stays — the UL16/17/18 campaigns
being kept use `.histo.root` through it, and the EGM/MUO/JMAR dual paths at `:2609`, `:2842`,
`:3014`, `:3091` serve those. Do not let this step grow into removing them.

Constraints: preserve the `$PROMPT_DATAMC` placeholder text in `AK4_parameters.py` (`autobtv`
`sed`s against it); confirm on the BTV list that nobody still runs these campaigns before deleting
data files.

→ verify: Phase 0 clean on Summer24, plus a grep sweep for orphaned references.

Benefit: removes the payloads that cannot survive the bump; deletes two coffea subpackage
dependencies. Complexity: medium (mechanical but wide). Risk: low-medium, fully revertible.
Files: `utils/AK4_parameters.py`, `utils/correction.py`, `helpers/func.py`, `data/JME/*`,
`data/LUM/Rereco17_94X/`.

### A3. Rewrite `cumsum()` awkward-1/2-portable

`BTA_helper.py:147-156` is the repo's only `ak.layout` use. Replace the layout surgery with
flatten → `np.cumsum` → re-offset → `ak.unflatten`, valid under both awkward versions.

→ verify: bit-identical `ak.to_numpy` comparison against current output on the BTA fileset — not an
eyeball review — plus a clean A0 BTA ROOT diff.

Benefit: removes the one confirmed hard rewrite from the migration. Complexity: low.
Risk: medium (feeds impact-parameter output consumed by `SFbc-2D`), bounded by A0.
Files: `helpers/BTA_helper.py`.

---

## Track B — the bump

### B1. Focused spike, 3 days *(reduced from 5 — the API questions are already answered)*

Parallel env: `coffea 2026.7.0`, `awkward>=2.8.11`, `uproot>=5.7.0`, `parsl>=2024.12.09`, numpy and
Python **held at current versions** to isolate the diff. Only runtime-behaviour questions remain:

1. **Vector numerics.** The names resolve, but in 2026.7.0 `ThreeVector`/`LorentzVector` subclass
   the standalone `vector` package's `MomentumAwkward3D`/`MomentumAwkward4D`
   (`vector.py:77` — `behavior.update(vector.backends.awkward.behavior)`). `calc_ip_vector()` uses
   `.cross()`, `.dot()` and `.p2` on these. Names being stable does not make the arithmetic
   identical — validate numerically against the A0 baseline.
2. **`PFNanoAODSchema` vs `update_branch.py`'s `missing_branch`** backfill on the custom NanoAOD.
3. **`rochester_lookup` signature** — historically the least stable of the `lookup_tools` imports.
4. **parsl Channels removal** — port one `HighThroughputExecutor` block, confirm `script_dir` lands
   correctly on the provider.
5. **`dask_jobqueue` API drift** for `HTCondorCluster` / `LPCCondorCluster`.

Deliverable: a go/no-go and a day count. **Nothing merges.**

### B2. Migration branch

Dependency bump (`setup.cfg`, `test_env.yml`) → parsl Channels port across all 9 executor blocks →
`correction.py` per-import verification → `condor*/execute.sh` (`condor/execute.sh:63` hardcodes
`python=3.10`) → CI matrix. Sequenced so each step is individually revertible. Python and numpy
bumps are a **separate, later** change — not part of this one.

### B3. Cutover

Old-env vs new-env Phase 0 diff on **identical input files**, per workflow, both `.coffea` and
`--isArray` ROOT. Decision 3's tolerance is the pass criterion. Then one real production batch in
parallel under both environments, on at least one cluster per executor type, before the pin on
`master` moves.

---

## Estimate

Track A: ~1.5 weeks (A1 is the bulk), and every step stands alone.
Track B: ~1.5 weeks after a clean spike, dominated by the parsl Channels port.

Down from the earlier ~3 weeks, because the executor port moved into the verifiable environment and
no API hunt is needed. The remaining uncertainty is concentrated in B1 item 1 — vector arithmetic
provenance — which is a numerical-validation question, not a compatibility one.

---

## Out of scope / deferred

- **Python 3.11+ and numpy 2.** Not required by coffea 2026.7.0. Deliberately deferred so the
  migration diff stays attributable. Python 3.10 EOL (October 2026) makes this a follow-up, not a
  non-issue.
  - *(2026-08-14)* Re-affirmed after `rabbit` (unrelated tensorflow-based fitting tool, checked out
    as a sibling directory of this repo) was pip-installed into the shared `commfw` conda env and
    dragged numpy to 2.2.6 there, breaking `coffea.util` (`awkward 1.10.5` reads the now-removed
    top-level `numpy.AxisError`; it lives at `numpy.exceptions.AxisError` since numpy 2.0). Fixed by
    giving `rabbit` its own venv (`rabbit/env/`, per its own README) and re-pinning `commfw` to
    `numpy==1.26.4` — i.e. by keeping this repo's env off numpy 2, not by moving it on. Confirms
    Track A/B should stay sequenced ahead of this item, not bundled with it.
  - **New scoping fact for whenever this item is picked up:** the plan's `numba>=0.58.1` floor (from
    coffea 2026.7.0's own METADATA) is *not* a numpy-2-safe floor. Numba only gained binary numpy 2.0
    compatibility at **0.60.0**; NEP 50 type-semantics weren't solid until **0.61–0.62**. A future
    numpy 2 bump needs `numba>=0.60` (prefer `>=0.61`) re-pinned and every numba-JIT'd path
    (`utils/correction.py`, `helpers/BTA_helper.py`'s numerics) re-verified against Phase 0 under it
    — this was not covered by Track B1's spike questions and should be added as its own item when
    this deferred work is scheduled.
- **`autobtv`.** Checked 2026-08-03 and parked. Two items before cutover: its image builds from the
  fork `github.com/ValVau/BTVNanoCommissioning.git` (`Dockerfile:49`) using this repo's
  `test_env.yml`, so the pin propagates *through that fork* — the migration is not done until it is
  synced or the Dockerfile repointed. Its inline merge block (`.gitlab-ci.yml:788-793`) uses
  `coffea.util.load/save` and `processor.accumulate`; both verified present in 2026.7.0. It also
  installs `parsl==2023.10.23` (`Dockerfile:54`) which will need to move past the Channels removal.
- **`gitlab.cern.ch/cms-btv/btv-sf-code`.** Not checked — subprojects could not be enumerated
  without API access. If those repos consume `.coffea`/ROOT *outputs* they are covered by B3; if any
  import this package's modules, that is a second compatibility obligation not costed here.
- **CLI surface contract.** `autobtv` depends on `--wf --json --year --campaign --executor
  --workers --chunk --retries --outputdir --limit`, plus `scripts/fetch.py` and
  `scripts/plotdataMC.py`. Nothing in this plan changes them; keep it that way.
