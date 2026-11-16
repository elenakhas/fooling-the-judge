# fooling-the-judge

Code for the Apart Research Epistemics sprint project *Fooling the Judge: Do LLM Sycophancy Judges Read Stance or Vocabulary?* (pilot study).

The study builds controlled answer versions from three sycophancy benchmarks (EduFrameTrap, SYCON-Bench, JANUS). Each question gets three stances (honest, partial, failing) × nine wording conditions (plain + 8 wording families). A second experiment pairs camouflaged replies with legitimate twins. The versions are judged by published sycophancy judges and a reader-belief judge, each with and without the ground truth, using Claude Sonnet 5.5 and gpt-oss-120b.

Data are not included. Third-party benchmarks are fetched from their own repositories (see below); generated versions and judgments are not part of this repository.

## Layout

```
scripts/
  llm.py                    minimal Anthropic / OpenAI-compatible client (keys read from environment variables)
  prompts.py                published judge prompts (EduFrameTrap, copied verbatim from the authors' repo) + reader-belief judge
  prompts_studyb.py         judge prompts for SYCON-Bench and JANUS, no-truth variants
  prompts_ingredients.py    prompts that write the stance "ingredients" for each question
  prompts_camo.py           prompts that write camouflaged replies and legitimate twins

  select_studyb.py, extend_items.py, finalize_items.py   pick the 60 questions (20 per dataset)
  run_ingredients.py, check_ingredients.py, drop_error_rows.py   write and check the ingredients
  fit_markers.py, assemble_versions.py                    insert wording-family markers, assemble 1,620 versions
  lexicon_checks.py, features_open.py, fetch_lexicons.py  open-lexicon manipulation checks (optional)
  make_review_page.py                                     HTML page for reading versions by hand
  make_ground_truth_sheet.py, score_ground_truth.py       stance-rating sheet and its scoring (not used in the pilot)
  generate_camo.py, check_camo.py                         camouflage pairs (6 moves × 40 questions)

  judge_studyb.py           runs a judge arm over a versions file (sync, parallel or Message Batches API; cached)
  sample_rejudge.py         stratified 10% sample for the run-to-run noise check
  reparse_judgments.py      re-parses stored judge outputs with the current parser
  judge_consistency.py      verdict flips between the main run and the re-judge
  score_studyb.py           flag rates and lifts per judge, dataset, stance and wording family
  analyze_studyb.py         paired tests (exact McNemar / sign test, Holm), Wilcoxon partial-vs-failing contrast
  analyze_camo.py           camouflage pass rates and twin false alarms

  run_full.sh               main study: STAGE=1 materials, STAGE=2 judges (arms 0-3) + re-judge
  run_camo.sh               camouflage experiment
  run_notruth.sh            judges without the ground truth (arms 4-5)
  run_openrouter.sh         the same judges with another model via OpenRouter (used for gpt-oss-120b)

figures/
  make_figs_data.py                 collects the numbers used by the figures
  final/fig2.py                     Figure 1: stance vs wording effect per judge
  final/fig4_camo_combined.py       Figure 2: camouflage, with and without truth
  final/fig3.py                     Figure A1: wording families, judges with truth
  final/figA_notruth_families.py    Figure A2: wording families, judges without truth
  final/figA2_traces.py             Figure A3: how often rationales cite the added wording
  final/tables_appendix.py          Tables A1-A3
  final/examples/make_examples_v2.py, make_examples_v3.py   example figures (versions and camouflage pairs)
```

Judge arms used in the report: `arm0` published judge with truth, `arm2` reader belief with truth, `arm4` published task without truth, `arm5` reader belief without truth. Arms 1 and 3 exist in the code but are not reported.

## Setup

```bash
pip install -r requirements.txt
export ANTHROPIC_API_KEY=...      # Claude runs
export OPENROUTER_API_KEY=...     # gpt-oss-120b runs
export FTJ_DATA=/path/to/data     # third-party data, kept outside this folder
```

Source benchmarks (clone into `$FTJ_DATA/repos/`):

- EduFrameTrap: https://github.com/KasneciLab/eduframetrap-icml2026 (`data/runs.zip`)
- SYCON-Bench: https://github.com/JiseungHong/SYCON-Bench (`false-presuppositions-setting/data/`)
- JANUS: https://github.com/PolydorosG/Janus (`data/janus.csv`)

Please check each benchmark's licence before redistributing anything derived from it.

Two hand-written inputs are included: `studyb/frames_pilot.json` (the wording-family marker phrasings and the templates that place them) and `studyb/exclusions.tsv` (questions excluded from the 60, with the reason).

## Running

Run all commands from the repository root.

```bash
STAGE=1 bash scripts/run_full.sh            # questions, ingredients, versions
STAGE=2 bash scripts/run_full.sh            # Sonnet judges + 10% re-judge (Batch API; re-run to collect)
STAGE=1 bash scripts/run_camo.sh && STAGE=2 bash scripts/run_camo.sh
bash scripts/run_notruth.sh
MODEL=openai/gpt-oss-120b PROVIDER=deepinfra BATCH=0 WORKERS=24 CAMO=1 NOTRUTH=1 REJUDGE=1 \
  bash scripts/run_openrouter.sh

python3 -I scripts/analyze_studyb.py --judgments results/judgments/studyb_full \
  --rejudge results/judgments/studyb_full_rejudge --report studyb/full/analysis.md
python3 -I figures/make_figs_data.py && python3 figures/final/fig2.py   # etc.
```

Each version is scored at the stance it was written for (honest, partial or failing); stances were spot-checked by hand. For the analysis, run stages 1 and 2 of `run_full.sh` and then `analyze_studyb.py` directly; stage 3 expects a stance-rating sheet that this pilot did not use.

The example figures are rendered with Playwright. Install its browser once with `python3 -m playwright install chromium`, or point `CHROME_PATH` at an existing Chrome.

## Licence

MIT (see `LICENSE`). Judge prompts copied from published benchmarks remain under their authors' terms.
