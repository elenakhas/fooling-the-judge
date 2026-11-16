#!/usr/bin/env bash
# Study B2 (camouflage vs legitimate twin). Needs ANTHROPIC_API_KEY. Run from the fooling-the-judge folder.
#   STAGE=1 bash scripts/run_camo.sh   generate the pairs (40 questions x 6 moves, Opus 5.5) -> checks -> spot-check sheet
#            TRIAL=2 STAGE=1 ...       first 2 questions per dataset only (4 x 6 = 24 pairs), to read before the rest
#   STAGE=2 bash scripts/run_camo.sh   judge all replies with arms 0-3 (Message Batches API; re-run to collect)
# Optional: MOVES=E1_frame_shift,E3_concession_pivot,... ; GEN_MODEL ; JUDGE_MODEL
set -euo pipefail
: "${ANTHROPIC_API_KEY:?Set ANTHROPIC_API_KEY first}"
: "${STAGE:?Set STAGE=1 or 2}"
C=studyb/camo; J=results/judgments/studyb_camo; mkdir -p "$C" "$J"
if [ "$STAGE" = "1" ]; then
  python3 -I scripts/generate_camo.py --items studyb/items_60.jsonl --ingredients studyb/full/ingredients.jsonl \
    --out "$C/generations.jsonl" --versions "$C/versions.jsonl" --model "${GEN_MODEL:-claude-opus-5-5}" ${MOCK:+--mock} \
    ${TRIAL:+--limit "$TRIAL"} ${MOVES:+--moves "$MOVES"}
  python3 -I scripts/check_camo.py --items studyb/items_60.jsonl --ingredients studyb/full/ingredients.jsonl \
    --generations "$C/generations.jsonl" --report "$C/checks.md" --sheet "$C/spotcheck_sheet.csv" --key "$C/spotcheck_KEY.jsonl"
  echo "Read $C/checks.md and a few pairs in $C/generations.jsonl; rate $C/spotcheck_sheet.csv (key stays closed)."
  exit 0
fi
while true; do
  status=""
  for arm in arm0 arm2 arm1 arm3; do
    out=$(python3 -I scripts/judge_studyb.py --versions "$C/versions.jsonl" --arm "$arm" --model "${JUDGE_MODEL:-claude-sonnet-5-5}" \
      --out-dir "$J" --temperature none --max-tokens 6000 --batch)
    echo "   $(echo "$out" | tail -1)"; status="$status $out"
  done
  case "$status" in *SUBMITTED*|*WAITING*) sleep "${POLL_SECONDS:-120}" ;; *) break ;; esac
done
echo "Done judging -> $J"
