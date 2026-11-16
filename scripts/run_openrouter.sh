#!/usr/bin/env bash
# Second judge family via OpenRouter. Batch API by default (about half price; the model must have a batch variant,
# see openrouter.ai/models?variant=batch); BATCH=0 uses ordinary parallel calls. Needs OPENROUTER_API_KEY.
#   MODEL=openai/gpt-oss-120b PROVIDER=deepinfra bash scripts/run_openrouter.sh        main study, arms 0-3
#   MODEL=openai/gpt-5.2 bash scripts/run_openrouter.sh                                 (OpenAI-only models need no PROVIDER)
#   TEST=5 ...        judge 5 versions into /tmp/or_test only, with ordinary calls (check parsing and cost first)
#   REASONING=low|medium|high|default   reasoning effort for reasoning models (default: medium, sent explicitly)
#   CAMO=1 ...        also the camouflage pairs;  NOTRUTH=1 ...  also arms 4 and 5 (EduFrameTrap + SYCON, as the Sonnet run)
#   REJUDGE=1 ...     also the 10% re-judge sample (studyb/full/rejudge_versions.jsonl), arms 0-3
#   TEMPERATURE=      default none (provider default), as the Sonnet runs
#   ARMS="arm0 arm2" ...   judge only these arms (default arm0 arm2 arm1 arm3), e.g. to fit a budget
# PROVIDER pins one provider with fallbacks off (reproducible); the provider that served each call is recorded.
set -euo pipefail
: "${OPENROUTER_API_KEY:?Set OPENROUTER_API_KEY first}"
: "${MODEL:?Set MODEL, e.g. openai/gpt-oss-120b}"
# extra request fields: provider pinning (fallbacks off) and an explicit reasoning effort, so both are fixed and recorded
BODY=$(python3 -I -c 'import json,os; b={}
p=os.environ.get("PROVIDER"); r=os.environ.get("REASONING","medium")
if p: b["provider"]={"order":[p],"allow_fallbacks":False}
if r and r!="default": b["reasoning"]={"effort":r}
print(json.dumps(b))')
EXTRA=(--extra-body "$BODY")
echo "model $MODEL | provider ${PROVIDER:-any (OpenRouter chooses)} | reasoning effort ${REASONING:-medium}"
TAG=$(echo "$MODEL" | tr '/:' '__')
ARGS=(--model "$MODEL" --provider openai --base-url "${BASE_URL:-https://openrouter.ai/api/v1}" --key-env OPENROUTER_API_KEY
      --temperature "${TEMPERATURE:-none}" --max-tokens "${MAX_TOKENS:-6000}" --workers "${WORKERS:-8}" "${EXTRA[@]}")
ARMS="${ARMS:-arm0 arm2 arm1 arm3}"; [ "${NOTRUTH:-0}" = "1" ] && ARMS="$ARMS arm4 arm5"
# no-truth arms judge the same datasets as the Sonnet run: EduFrameTrap + SYCON (WORDING_ONLY=1 adds JANUS on the main versions)
NT_DS="EduFrameTrap,SYCON-Bench"; NT_DS_MAIN="$NT_DS"; [ "${WORDING_ONLY:-0}" = "1" ] && NT_DS_MAIN="$NT_DS,JANUS"
if [ -n "${TEST:-}" ]; then
  python3 -I scripts/judge_studyb.py --versions studyb/full/versions.jsonl --arm arm2 "${ARGS[@]}" --out-dir /tmp/or_test --limit "$TEST"
  echo "Test done: /tmp/or_test (send it to Claude before the full run)"; exit 0
fi
JOBS=()
for arm in $ARMS; do
  OUT=results/judgments/studyb_full_$TAG; DM=all; DC=all
  if [ "$arm" = arm4 ] || [ "$arm" = arm5 ]; then OUT=results/judgments/studyb_notruth_$TAG; DM=$NT_DS_MAIN; DC=$NT_DS; fi
  JOBS+=("studyb/full/versions.jsonl|$arm|$OUT|$DM")
  [ "${CAMO:-0}" = "1" ] && [ -f studyb/camo/versions.jsonl ] && JOBS+=("studyb/camo/versions.jsonl|$arm|results/judgments/studyb_camo_$TAG|$DC")
  if [ "${REJUDGE:-0}" = "1" ] && { [ "$arm" = arm0 ] || [ "$arm" = arm1 ] || [ "$arm" = arm2 ] || [ "$arm" = arm3 ]; }; then
    [ -f studyb/full/rejudge_versions.jsonl ] || { echo "studyb/full/rejudge_versions.jsonl missing"; exit 1; }
    JOBS+=("studyb/full/rejudge_versions.jsonl|$arm|results/judgments/studyb_full_rejudge_$TAG|all")
  fi
done
dsarg() { [ "$1" = all ] || echo "--datasets $1"; }
if [ "${BATCH:-1}" = "0" ]; then
  for j in "${JOBS[@]}"; do IFS='|' read -r V ARM OUT D <<< "$j"
    python3 -I scripts/judge_studyb.py --versions "$V" --arm "$ARM" "${ARGS[@]}" --out-dir "$OUT" $(dsarg "$D"); done
else
  echo "Batch API: submitting, then checking every ${POLL_SECONDS:-120} s (Ctrl-C is safe; re-run the same command to collect)"
  while true; do
    status=""
    for j in "${JOBS[@]}"; do IFS='|' read -r V ARM OUT D <<< "$j"
      out=$(python3 -I scripts/judge_studyb.py --versions "$V" --arm "$ARM" "${ARGS[@]}" --out-dir "$OUT" --batch $(dsarg "$D"))
      echo "   $(basename "$OUT") $(echo "$out" | tail -1)"; status="$status $out"
    done
    case "$status" in *SUBMITTED*|*WAITING*) sleep "${POLL_SECONDS:-120}" ;; *) break ;; esac
  done
fi
echo "Done. Judgments in results/judgments/*_$TAG (do not open before your ratings are done)."
