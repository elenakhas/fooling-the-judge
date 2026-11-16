"""Study B2: generate camouflaged replies and their legitimate twins (one call per question x move).

  python3 -I scripts/generate_camo.py --items studyb/items_60.jsonl --ingredients studyb/full/ingredients.jsonl \
      --out studyb/camo/generations.jsonl --versions studyb/camo/versions.jsonl [--moves E1_frame_shift,E3_concession_pivot]
      [--model claude-opus-5-5] [--workers 4] [--limit N] [--mock] [--dry-run]

Reuses the 60 questions and their checked ingredients (EduFrameTrap and SYCON only; JANUS is skipped). Default: all
6 family-E moves, i.e. 40 questions x 6 moves = 240 calls, 480 replies. Re-running skips pairs already in --out.
--versions writes judge-ready rows (same format as studyb/full/versions.jsonl): stance "failing" for the camouflaged
reply and "honest" for the twin, family = the move, so judge_studyb.py and run_full's batching can judge them as-is,
and the MVP's plain versions of the same questions serve as the no-move baseline.
"""
import argparse, concurrent.futures, datetime, json, os, re, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from prompts_camo import MOVES, DEFAULT_MOVES, render
from assemble_versions import context
from llm import call, get_key


def parse(raw):
    m = re.search(r"\{.*\}", raw or "", re.S)
    if not m:
        return None, "no JSON"
    try:
        o = json.loads(m.group())
    except json.JSONDecodeError:
        try:
            o = json.loads(re.sub(r",\s*([}\]])", r"\1", m.group()))
        except json.JSONDecodeError as e:
            return None, f"bad JSON: {e}"
    if not (isinstance(o.get("camouflaged"), str) and isinstance(o.get("twin"), str)):
        return None, "missing camouflaged/twin"
    return o, None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--items", required=True)
    ap.add_argument("--ingredients", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--versions", required=True)
    ap.add_argument("--moves", default=",".join(DEFAULT_MOVES))
    ap.add_argument("--model", default="claude-opus-5-5")
    ap.add_argument("--temperature", default="none")
    ap.add_argument("--max-tokens", type=int, default=8000)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--limit", type=int, default=None, help="trial run: only the first N questions of each dataset")
    ap.add_argument("--mock", action="store_true", help="fake replies (plumbing test)")
    ap.add_argument("--dry-run", action="store_true", help="print one rendered prompt per dataset and stop")
    a = ap.parse_args()
    moves = [m.strip() for m in a.moves.split(",") if m.strip()]
    bad = [m for m in moves if m not in MOVES]
    if bad:
        sys.exit(f"unknown moves {bad}; choose from {list(MOVES)}")
    temp = None if a.temperature.lower() == "none" else float(a.temperature)
    items = [json.loads(l) for l in open(a.items)]
    items = [it for it in items if it["source"] in ("EduFrameTrap", "SYCON-Bench")]
    if a.limit:   # trial: the first N questions of EACH dataset
        items = [it for ds in ("EduFrameTrap", "SYCON-Bench") for it in [x for x in items if x["source"] == ds][: a.limit]]
    ings = {json.loads(l)["base_id"]: (json.loads(l).get("ingredients") or {}) for l in open(a.ingredients)}
    jobs = [(it, mv) for it in items for mv in moves if ings.get(it["base_id"], {}).get("honest_core")]
    skipped = [it["base_id"] for it in items if not ings.get(it["base_id"], {}).get("honest_core")]
    if skipped:
        print(f"skipping (no honest_core): {' '.join(skipped)}")
    if a.dry_run:
        seen = set()
        for it, mv in jobs:
            if it["source"] in seen:
                continue
            seen.add(it["source"])
            s, u = render(it, ings[it["base_id"]], mv)
            print(f"===== {it['base_id']} / {mv}\n--- SYSTEM ---\n{s}\n--- USER ---\n{u}\n")
        print(f"[dry-run] {len(jobs)} calls ({len(items)} questions x {len(moves)} moves)")
        return
    key = None if a.mock else get_key("anthropic")
    if not a.mock and not key:
        sys.exit("Set ANTHROPIC_API_KEY first.")
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    done = set()
    if os.path.exists(a.out):
        for l in open(a.out):
            r = json.loads(l)
            if not r.get("parse_error"):
                done.add((r["base_id"], r["move"]))
    todo = [(it, mv) for it, mv in jobs if (it["base_id"], mv) not in done]
    print(f"{len(jobs)} pairs, {len(done)} already done, {len(todo)} to generate")

    def work(job):
        it, mv = job
        s, u = render(it, ings[it["base_id"]], mv)
        if a.mock:
            raw, usage = json.dumps({"camouflaged": f"[mock camouflaged {mv}] " + ings[it['base_id']]["honest_core"],
                                     "twin": f"[mock twin {mv}] " + ings[it['base_id']]["honest_core"],
                                     "move_sentence_camouflaged": "", "move_sentence_twin": "", "notes": ""}), {}
        else:
            raw, usage = call("anthropic", "", a.model, key, s, u, temp, a.max_tokens, return_usage=True)
        o, err = parse(raw)
        return {"base_id": it["base_id"], "source": it["source"], "move": mv, "model": "MOCK" if a.mock else a.model,
                "date": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "raw": raw, "pair": o,
                "parse_error": err, "usage": usage}

    with open(a.out, "a") as f, concurrent.futures.ThreadPoolExecutor(a.workers) as ex:
        for r in ex.map(work, todo):
            f.write(json.dumps(r, ensure_ascii=False) + "\n"); f.flush()
            print(f"{r['base_id']} {r['move']}: {'ok' if not r['parse_error'] else 'ERROR ' + r['parse_error']}")
    # judge-ready versions from every parsed pair
    by_id = {it["base_id"]: it for it in items}
    latest = {}
    for l in open(a.out):
        r = json.loads(l)
        if not r.get("parse_error") and r["base_id"] in by_id and r["move"] in moves:
            latest[(r["base_id"], r["move"])] = r
    n = 0
    with open(a.versions, "w") as f:
        for (bid, mv), r in sorted(latest.items()):
            it = by_id[bid]
            for stance, key_ in (("failing", "camouflaged"), ("honest", "twin")):
                row = {"version_id": f"{bid}::{stance}::{mv}::camo", "example_id": f"{bid}::{stance}::{mv}::camo",
                       "base_id": bid, "dataset": it["source"], "clarity": "quiet", "stance": stance, "family": mv,
                       "frame_variant": 0, "study": "B2_camouflage", "pair_role": key_,
                       "move_sentence": r["pair"].get(f"move_sentence_{key_}", ""), "t2": r["pair"][key_].strip(),
                       "response": r["pair"][key_].strip(), "n_words": len(r["pair"][key_].split()),
                       "ingredient_model": r["model"]}
                row.update(context(it))
                f.write(json.dumps(row, ensure_ascii=False) + "\n"); n += 1
    tok = [json.loads(l).get("usage") or {} for l in open(a.out)]
    print(f"{n} judge-ready versions -> {a.versions}; tokens so far: "
          f"{sum(t.get('input_tokens', 0) for t in tok):,} in, {sum(t.get('output_tokens', 0) for t in tok):,} out")


if __name__ == "__main__":
    main()
