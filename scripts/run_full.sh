#!/usr/bin/env bash
# Study B full run (v0.5d, 60 questions, up to 1,620 versions). Needs ANTHROPIC_API_KEY. Run from the fooling-the-judge folder.
#
#   STAGE=1 bash scripts/run_full.sh   ingredients for the 65 candidates -> 60 questions -> versions -> review page and the
#                                      blind rating sheet (all partials + 30 honest/failing fillers). No judging.
#                                      To exclude questions, add them with the reason to studyb/exclusions.tsv and rerun.
#   (time-stamp the pre-registration together with studyb/full/FROZEN.sha256)
#   STAGE=2 bash scripts/run_full.sh   judges (arms 0-3) and the 10% re-judge. Batch API by default (half price; most batches
#                                      finish within an hour). Safe to stop and re-run: it collects finished batches and
#                                      keeps waiting. DO NOT open the judgment files until your rating is done.
#   (rate ground_truth_sheet.csv, save it as ground_truth_RATED.csv)
#   STAGE=3 bash scripts/run_full.sh   scores the rating, then the judgments
#
# Optional: INGREDIENT_MODEL, JUDGE_MODEL, BATCH=0 (ordinary calls instead of batches), JUDGE_WORKERS (parallel calls when
# BATCH=0, default 8), REDO_ROUNDS (default 2), EXCLUDE (comma-separated base_ids), FILLERS (default 30)
set -euo pipefail
: "${ANTHROPIC_API_KEY:?Set ANTHROPIC_API_KEY first}"
: "${STAGE:?Set STAGE=1, 2 or 3}"
ING_MODEL="${INGREDIENT_MODEL:-claude-opus-5-5}"
JUDGE="${JUDGE_MODEL:-claude-sonnet-5-5}"
P=studyb/full; J=results/judgments/studyb_full; FR=studyb/frames_pilot.json; ITEMS=studyb/items_60.jsonl
mkdir -p "$P" "$J"

if [ "$STAGE" = "1" ]; then
  echo "== 1 ingredients for 65 candidates ($ING_MODEL)"
  python3 -I scripts/run_ingredients.py --items studyb/items_candidates.jsonl --out "$P/ingredients.jsonl" --model "$ING_MODEL"
  echo "== 2 pick the 60 questions (first 10 SYCON candidates with a true kernel)"
  python3 -I scripts/finalize_items.py --candidates studyb/items_candidates.jsonl --ingredients "$P/ingredients.jsonl" \
    --out "$ITEMS" --exclude-file studyb/exclusions.tsv --exclude "${EXCLUDE:-}"
  echo "== 3 ingredient checks (questions with ERRORs are regenerated automatically, up to ${REDO_ROUNDS:-2} rounds)"
  for round in $(seq 0 "${REDO_ROUNDS:-2}"); do
    python3 -I scripts/check_ingredients.py --items "$ITEMS" --ingredients "$P/ingredients.jsonl" \
      --report "$P/ingredients_check.md" --sheet "$P/ingredients_review.csv" > /dev/null || true
    [ "$round" = "${REDO_ROUNDS:-2}" ] && break
    BAD=$(python3 -I scripts/drop_error_rows.py --ingredients "$P/ingredients.jsonl" --report "$P/ingredients_check.md")
    [ -z "$BAD" ] && break
    echo "   regenerating (round $((round+1))): $BAD"
    python3 -I scripts/run_ingredients.py --items "$ITEMS" --out "$P/ingredients.jsonl" --model "$ING_MODEL"
  done
  grep -m1 "items ·" "$P/ingredients_check.md" || true
  echo "== 4 fit markers"
  python3 -I scripts/fit_markers.py --items "$ITEMS" --ingredients "$P/ingredients.jsonl" --frames "$FR" \
    --out "$P/markers_fitted.jsonl" --report "$P/markers_check.md" --model "$ING_MODEL"
  echo "== 5 assemble versions"
  python3 -I scripts/assemble_versions.py --items "$ITEMS" --ingredients "$P/ingredients.jsonl" --frames "$FR" \
    --fitted "$P/markers_fitted.jsonl" --out "$P/versions.jsonl" --report "$P/versions_check.md" || true
  echo "== 6 lexicon checks"
  python3 -I scripts/lexicon_checks.py --items "$ITEMS" --ingredients "$P/ingredients.jsonl" --versions "$P/versions.jsonl" \
    --report "$P/lexicon_checks.md" --csv "$P/lexicon_features.csv" --frames "$FR" || echo "   (lexicon checks skipped)"
  echo "== 7 review page (no judge results) and blind ground-truth sheet"
  python3 -I scripts/make_review_page.py --items "$ITEMS" --ingredients "$P/ingredients.jsonl" --versions "$P/versions.jsonl" \
    --frames "$FR" --fitted "$P/markers_fitted.jsonl" --html "$P/review.html" --csv "$P/review.csv"
  python3 -I scripts/make_ground_truth_sheet.py --items "$ITEMS" --versions "$P/versions.jsonl" \
    --sheet "$P/ground_truth_sheet.csv" --key "$P/ground_truth_KEY.jsonl" --fillers "${FILLERS:-30}"
  shasum -a 256 "$ITEMS" "$FR" "$P/ingredients.jsonl" "$P/markers_fitted.jsonl" "$P/versions.jsonl" > "$P/FROZEN.sha256"
  echo "Done. Read $P/ingredients_check.md and review.html; rate $P/ground_truth_sheet.csv (do NOT open the KEY file)."
  echo "Hashes of the frozen materials: $P/FROZEN.sha256 (time-stamp them with the pre-registration)."
  exit 0
fi

JARGS=(--model "$JUDGE" --temperature none --max-tokens 6000)
[ "${JUDGE_MOCK:-0}" = "1" ] && JARGS+=(--mock)     # plumbing test only
if [ "$STAGE" = "2" ]; then
  echo "== 1 check frozen materials"
  shasum -a 256 -c "$P/FROZEN.sha256"
  [ -f "$P/rejudge_versions.jsonl" ] || python3 -I scripts/sample_rejudge.py --versions "$P/versions.jsonl" --out "$P/rejudge_versions.jsonl"
  if [ "${BATCH:-1}" = "0" ]; then
    echo "== 2 judges ($JUDGE), arms 0-3, ordinary calls; then the 10% re-judge"
    for spec in "$P/versions.jsonl|$J" "$P/rejudge_versions.jsonl|${J}_rejudge"; do
      for arm in arm0 arm2 arm1 arm3; do
        python3 -I scripts/judge_studyb.py --versions "${spec%%|*}" --arm "$arm" --out-dir "${spec##*|}" "${JARGS[@]}" \
          --workers "${JUDGE_WORKERS:-8}"
      done
    done
  else
    echo "== 2 judges ($JUDGE), arms 0-3 + 10% re-judge, Message Batches API (checks every 2 minutes; Ctrl-C is safe)"
    while true; do
      status=""
      for spec in "$P/versions.jsonl|$J" "$P/rejudge_versions.jsonl|${J}_rejudge"; do
        for arm in arm0 arm2 arm1 arm3; do
          out=$(python3 -I scripts/judge_studyb.py --versions "${spec%%|*}" --arm "$arm" --out-dir "${spec##*|}" "${JARGS[@]}" --batch)
          echo "   $(basename "${spec##*|}") $(echo "$out" | tail -1)"
          status="$status $out"
        done
      done
      case "$status" in *SUBMITTED*|*WAITING*) sleep "${POLL_SECONDS:-120}" ;; *) break ;; esac
    done
    case "$status" in *GAVE_UP*) echo "Some prompts failed 3 times; rerun STAGE=2 later to retry, or continue (they count as missing)." ;; esac
  fi
  echo "Done judging. Do not open $J until your rating is finished; then run STAGE=3."
  exit 0
fi

echo "== 1 check frozen materials"
shasum -a 256 -c "$P/FROZEN.sha256"
ls "$J"/*.batch.json "${J}_rejudge"/*.batch.json >/dev/null 2>&1 && { echo "Batches still open: run STAGE=2 first"; exit 1; }
echo "== 2 score the blind rating"
: "${RATED:=$P/ground_truth_RATED.csv}"
[ -f "$RATED" ] || { echo "Missing $RATED (your rated copy of ground_truth_sheet.csv)"; exit 1; }
python3 -I scripts/score_ground_truth.py --sheet "$RATED" --key "$P/ground_truth_KEY.jsonl" --versions "$P/versions.jsonl" \
  --out "$P/confirmed.json" --report "$P/ground_truth.md"
echo "== 2b re-parse stored answers with the current parser (no API calls)"
python3 -I scripts/reparse_judgments.py "$J"/*.jsonl "${J}_rejudge"/*.jsonl
echo "== 3 noise (re-judge vs main run)"
python3 -I scripts/judge_consistency.py "$J" "${J}_rejudge" --report "$P/consistency.md" > /dev/null
echo "== 4 scores (main: reader-belief three-step shift + yes/no flags with rule S; secondary: JANUS rule M with strict confirmation)"
python3 -I scripts/score_studyb.py "$J"/*.jsonl --confirmed "$P/confirmed.json" --janus-belief-rule S --report "$P/scores.md" > /dev/null
python3 -I scripts/score_studyb.py "$J"/arm2*.jsonl --confirmed "$P/confirmed_janus_strict.json" --janus-belief-rule M --report "$P/scores_janus_rule_M.md" > /dev/null
python3 -I scripts/analyze_studyb.py --judgments "$J" --rejudge "${J}_rejudge" --confirmed "$P/confirmed.json" --report "$P/analysis.md" > /dev/null
python3 -I scripts/make_review_page.py --items "$ITEMS" --ingredients "$P/ingredients.jsonl" --versions "$P/versions.jsonl" \
  --judgments "$J" --frames "$FR" --fitted "$P/markers_fitted.jsonl" --html "$P/review_judged.html" --csv "$P/review_judged.csv"
echo "Done. Read $P/ground_truth.md, $P/analysis.md (pre-registered tests), $P/scores.md, $P/scores_janus_rule_M.md, $P/consistency.md, $P/review_judged.html"
