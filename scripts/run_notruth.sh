#!/usr/bin/env bash
# No-truth judges (exploratory): arm4 = published-judge task, arm5 = reader belief, both WITHOUT the reference answer,
# correction or fact list (EduFrameTrap: without the tutor's first reply and the student's pushback). Batch API.
# Judges the main study's EduFrameTrap + SYCON versions and, if present, the camouflage pairs. Needs ANTHROPIC_API_KEY.
#   bash scripts/run_notruth.sh            (re-run to collect; safe to stop)
#   WORDING_ONLY=1 bash scripts/run_notruth.sh   also judges JANUS with summary-only (wording-only) judges
set -euo pipefail
: "${ANTHROPIC_API_KEY:?Set ANTHROPIC_API_KEY first}"
JUDGE="${JUDGE_MODEL:-claude-sonnet-5-5}"
DS="EduFrameTrap,SYCON-Bench"; [ "${WORDING_ONLY:-0}" = "1" ] && DS="$DS,JANUS"
SPECS=("studyb/full/versions.jsonl|results/judgments/studyb_notruth|$DS")
[ -f studyb/camo/versions.jsonl ] && SPECS+=("studyb/camo/versions.jsonl|results/judgments/studyb_camo|EduFrameTrap,SYCON-Bench")
while true; do
  status=""
  for spec in "${SPECS[@]}"; do
    IFS='|' read -r V OUT D <<< "$spec"
    for arm in arm4 arm5; do
      out=$(python3 -I scripts/judge_studyb.py --versions "$V" --arm "$arm" --model "$JUDGE" --out-dir "$OUT" \
        --temperature none --max-tokens 6000 --datasets "$D" --batch ${JUDGE_MOCK:+--mock})
      echo "   $(basename "$OUT") $(echo "$out" | tail -1)"; status="$status $out"
    done
  done
  case "$status" in *SUBMITTED*|*WAITING*) sleep "${POLL_SECONDS:-120}" ;; *) break ;; esac
done
echo "Done. Send results/judgments/studyb_notruth/ and the arm4/arm5 files in results/judgments/studyb_camo/."
