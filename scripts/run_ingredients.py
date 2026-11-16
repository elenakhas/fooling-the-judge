"""Generate the ingredients: one model call per base item, JSON out.

  python3 -I run_ingredients.py --items ../studyb/items_candidates.jsonl --out ../studyb/full/ingredients.jsonl \
      --model claude-opus-5-5 [--dry-run] [--limit N]

Writes one row per item: base_id, source, model, settings, raw response, parsed ingredients (or parse_error),
token usage. Re-running skips items already present (delete the row to regenerate).
Thinking models (e.g. Opus 5.5) may reject a temperature setting: default is to omit it (--temperature none).
"""
import argparse, datetime, json, os, re, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from prompts_ingredients import render, FIELDS
from llm import call, get_key


def parse_json(text):
    m = re.search(r"\{.*\}", text or "", re.S)
    if not m:
        return None, "no JSON object found"
    try:
        return json.loads(m.group()), None
    except json.JSONDecodeError as e:
        return None, f"invalid JSON: {e}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--items", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--model", default="claude-opus-5-5")
    ap.add_argument("--provider", default="anthropic", choices=["anthropic", "openai"])
    ap.add_argument("--base-url", default="https://api.openai.com/v1")
    ap.add_argument("--key-env", default=None)
    ap.add_argument("--temperature", default="none", help="float, or 'none' to omit (thinking models)")
    ap.add_argument("--max-tokens", type=int, default=8000)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    temp = None if a.temperature.lower() == "none" else float(a.temperature)

    items = [json.loads(l) for l in open(a.items)][: a.limit]
    if a.dry_run:
        for it in items:
            s, u = render(it)
            print(f"===== {it['base_id']} ({it['source']}) — expects keys {FIELDS[it['source']]}\n{u[:400]}…\n")
        print(f"[dry-run] {len(items)} prompts rendered OK")
        return

    key = get_key(a.provider, a.key_env)
    if not key:
        sys.exit("No API key in environment (ANTHROPIC_API_KEY, or --key-env).")
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    done = set()
    if os.path.exists(a.out):
        done = {json.loads(l)["base_id"] for l in open(a.out)}
    with open(a.out, "a") as f:
        for it in items:
            if it["base_id"] in done:
                continue
            s, u = render(it)
            text, usage = call(a.provider, a.base_url, a.model, key, s, u, temp, a.max_tokens, return_usage=True)
            parsed, err = parse_json(text)
            if parsed is not None:
                missing = [k for k in FIELDS[it["source"]] if k not in parsed]
                if missing:
                    err = f"missing keys: {missing}"
            row = {"base_id": it["base_id"], "source": it["source"], "model": a.model,
                   "settings": {"temperature": temp, "max_tokens": a.max_tokens, "provider": a.provider},
                   "date": datetime.datetime.utcnow().isoformat(timespec="seconds") + "Z",
                   "raw": text, "ingredients": parsed, "parse_error": err, "usage": usage}
            f.write(json.dumps(row) + "\n"); f.flush()
            print(f"{it['base_id']}: {'OK' if not err else 'ERROR ' + err}  usage={usage}")


if __name__ == "__main__":
    main()
