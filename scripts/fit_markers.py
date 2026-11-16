"""Fit the marker phrasings assigned to each question to its topic, minimally and stance-blind (v0.3b).

  python3 -I scripts/fit_markers.py --items studyb/pilot_items.jsonl --ingredients studyb/pilot3/ingredients.jsonl \
      --frames studyb/frames_pilot.json --out studyb/pilot3/markers_fitted.jsonl --report studyb/pilot3/markers_check.md \
      [--model claude-opus-5-5] [--mock] [--dry-run]

Question i of a dataset is assigned phrasing i of each pool (same rule as assemble_versions.py). One model call per
question adapts those phrasings to the topic. The model sees only the topic (misconception / question / scenario),
never the honest, failing or partial text, and the result is used in all three stances of that question.

Checks per phrasing (any failure -> the original phrasing is used, and the report says why):
  - same grammatical ending (whole sentence / ':' / ',' / ends in a word such as 'that'), so the frame still reads;
  - at most 4 words replaced or added (difflib on words);
  - no new verdict words (correct, wrong, true, false, right, important, …) and no new numbers;
  - for hedges, boosters, concession and warmth: still recognised by the same lexicon dimension if the original was
    (needs the lexicons in $FTJ_DATA; skipped otherwise).
Swap (v0.3d, Lena 14 Nov): if the assigned phrasing still reads awkwardly after a 4-word adaptation, the model may pick
one of the pool's SPARE phrasings instead (pools have 22 phrasings for 20 questions, so the last ones are unused).
Each spare is given to at most one question per dataset, so no phrasing repeats; the swap is checked the same way and
listed in the report. Re-running skips questions already in --out.
"""
import argparse, datetime, difflib, json, os, re, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from prompts_ingredients import render_marker_fit
from assemble_versions import markers, question_order, resolve
from llm import call, get_key

VERDICT = ["correct", "incorrect", "wrong", "true", "false", "right", "mistaken", "important", "material",
           "minor", "accurate", "inaccurate", "error", "myth"]
LEX_TARGET = {"hedge": "hedging", "booster": "certainty", "concession": "concession", "warmth": "warmth"}


def ending(p):
    p = p.strip()
    return {".": "sentence", "!": "sentence", "?": "sentence", ":": "colon", ",": "comma"}.get(p[-1:], "word")


def words(p):
    return re.findall(r"[A-Za-z0-9'’%-]+", p.lower().replace("’", "'"))


def n_changed(a, b):
    sm = difflib.SequenceMatcher(None, words(a), words(b))
    return sum(max(j2 - j1, i2 - i1) for op, i1, i2, j1, j2 in sm.get_opcodes() if op != "equal")


def lex_dims():
    try:
        import lexicon_checks as L
        if not any(L.FO.lexicon_status().values()):
            return None
        return lambda t: L.features(t, tools=False)[0]
    except Exception:
        return None


def check(fam, orig, fit, feat):
    issues = []
    if not fit or not isinstance(fit, str):
        return ["no phrasing returned"]
    if ending(orig) != ending(fit):
        issues.append(f"ending changed ({ending(orig)} -> {ending(fit)})")
    if ending(orig) == "word" and words(orig)[-1:] != words(fit)[-1:]:
        issues.append(f"last word changed ('{words(orig)[-1]}' -> '{words(fit)[-1] if words(fit) else ''}')")
    k = n_changed(orig, fit)
    if k > 4:
        issues.append(f"{k} words changed (max 4)")
    new = set(words(fit)) - set(words(orig))
    bad = sorted(w for w in new if w in VERDICT)
    if bad:
        issues.append(f"new verdict words {bad}")
    if re.findall(r"\d", fit) != re.findall(r"\d", orig):
        issues.append("numbers changed")
    if feat and fam in LEX_TARGET:
        d = "dim_" + LEX_TARGET[fam]
        if feat(orig)[d] > 0 and feat(fit)[d] == 0:
            issues.append(f"no longer recognised as {LEX_TARGET[fam]} by the lexicons")
    return issues


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--items", required=True)
    ap.add_argument("--ingredients", required=True, help="only reframe_setting is read (some JANUS scope phrasings use it)")
    ap.add_argument("--frames", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--report", required=True)
    ap.add_argument("--model", default="claude-opus-5-5")
    ap.add_argument("--provider", default="anthropic", choices=["anthropic", "openai"])
    ap.add_argument("--base-url", default="https://api.openai.com/v1")
    ap.add_argument("--key-env", default=None)
    ap.add_argument("--temperature", default="none")
    ap.add_argument("--max-tokens", type=int, default=4000)
    ap.add_argument("--mock", action="store_true", help="return the phrasings unchanged (plumbing test)")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    temp = None if a.temperature.lower() == "none" else float(a.temperature)
    items = {json.loads(l)["base_id"]: json.loads(l) for l in open(a.items)}
    ings = {json.loads(l)["base_id"]: (json.loads(l).get("ingredients") or {}) for l in open(a.ingredients)}
    frames = json.load(open(a.frames))
    order = question_order(items)
    feat = lex_dims()

    done = set()
    if os.path.exists(a.out) and not a.dry_run:
        # keep cached fits only if the question is still in the set and still has the same assigned phrasings;
        # adding or dropping a question shifts the order, so later questions are refitted
        rows, stale = [json.loads(l) for l in open(a.out) if l.strip()], []
        keep = []
        for r in rows:
            b = r["base_id"]
            cur = markers(frames, items[b]["source"], order[b],
                          (ings.get(b, {}).get("reframe_setting") or "").strip()) if b in items else None
            if cur is not None and all(r["markers"].get(f, {}).get("assigned", r["markers"].get(f, {}).get("original")) == cur[f]
                                       for f in cur):
                keep.append(r); done.add(b)
            else:
                stale.append(b)
        if stale:
            print(f"refitting {len(stale)} question(s) whose assigned phrasings changed or that left the set: {' '.join(stale)}")
            with open(a.out, "w") as f:
                f.writelines(json.dumps(r, ensure_ascii=False) + "\n" for r in keep)
    key = None if (a.mock or a.dry_run) else get_key(a.provider, a.key_env)
    if not (a.mock or a.dry_run) and not key:
        sys.exit("No API key in environment.")
    if not a.dry_run:
        os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    out = open(a.out, "a") if not a.dry_run else None
    n_q = {}
    for b, it in items.items():
        n_q[it["source"]] = n_q.get(it["source"], 0) + 1
    taken = set()          # (dataset, family, spare index) already given to a question
    if os.path.exists(a.out) and not a.dry_run:
        for l in open(a.out):
            r = json.loads(l)
            for fam, m in r["markers"].items():
                if m.get("swap") is not None:
                    taken.add((r["dataset"], fam, m["swap"]))

    def spares(ds, fam, reframe):
        pool = resolve(frames["pools"], fam, ds)
        if not reframe:
            pool = [p for p in pool if "{reframe}" not in p]
        return [(j, pool[j].replace("{reframe}", reframe or "")) for j in range(n_q[ds], len(pool))
                if (ds, fam, j) not in taken]

    for bid in sorted(items):
        if bid in done:
            continue
        item = items[bid]
        ds = item["source"]
        reframe = (ings.get(bid, {}).get("reframe_setting") or "").strip()
        M = markers(frames, ds, order[bid], reframe)
        SP = {fam: spares(ds, fam, reframe) for fam in M}
        s, u = render_marker_fit(item, M, {fam: [t for _, t in v] for fam, v in SP.items()})
        if a.dry_run:
            print(f"===== {bid}\n{u}\n"); continue
        usage = {}
        if a.mock:
            got, raw = dict(M), "MOCK"
        else:
            raw, usage = call(a.provider, a.base_url, a.model, key, s, u, temp, a.max_tokens, return_usage=True)
            m = re.search(r"\{.*\}", raw or "", re.S)
            try:
                got = json.loads(m.group()) if m else {}
            except json.JSONDecodeError:
                got = {}
        res = {}
        alts = got.get("_alternatives") if isinstance(got.get("_alternatives"), dict) else {}
        for fam, assigned in M.items():
            fit, orig, swap = got.get(fam), assigned, None
            k = alts.get(fam)
            if isinstance(k, int) and 1 <= k <= len(SP[fam]):
                swap, orig = SP[fam][k - 1]
            issues = check(fam, orig, fit, feat)
            if swap is not None and issues:          # a failed swap falls back to the assigned phrasing
                swap, orig = None, assigned
            if swap is not None:
                taken.add((ds, fam, swap))
            res[fam] = {"assigned": assigned, "original": orig, "swap": swap, "fitted": fit,
                        "changed": bool(fit) and fit.strip() != assigned.strip(),
                        "issues": issues, "used": orig if issues else fit.strip()}
        row = {"base_id": bid, "dataset": item["source"], "model": "MOCK" if a.mock else a.model,
               "date": datetime.datetime.utcnow().isoformat(timespec="seconds") + "Z", "raw": raw,
               "markers": res, "usage": usage}
        out.write(json.dumps(row, ensure_ascii=False) + "\n"); out.flush()
        n_ch = sum(r["changed"] and not r["issues"] for r in res.values())
        n_bad = sum(bool(r["issues"]) for r in res.values())
        print(f"{bid}: {n_ch} phrasings adapted ({sum(r['swap'] is not None for r in res.values())} swapped), {n_bad} rejected (original kept)")
    if a.dry_run:
        return
    out.close()
    # report over the whole file
    R = ["# Marker fitting\n", "Phrasings adapted to each question's topic (stance-blind); an awkward one may be swapped for an unused "
         "spare phrasing of the same pool. Rejected adaptations fall back to the original.\n", "| question | family | original | used | note |", "|---|---|---|---|---|"]
    tot = ch = rej = 0
    for l in open(a.out):
        r = json.loads(l)
        for fam, m in r["markers"].items():
            tot += 1
            if m["issues"]:
                rej += 1
                R.append(f"| {r['base_id']} | {fam} | {m['original']} | {m['used']} | REJECTED: {'; '.join(m['issues'])} (proposed: {m['fitted']}) |")
            elif m.get("swap") is not None:
                ch += 1
                R.append(f"| {r['base_id']} | {fam} | {m['assigned']} | **{m['used']}** | swapped for spare phrasing {m['swap']} |")
            elif m["changed"]:
                ch += 1
                R.append(f"| {r['base_id']} | {fam} | {m['original']} | **{m['used']}** | adapted |")
    R.insert(2, f"**{tot} phrasings · {ch} adapted · {rej} rejected · {tot - ch - rej} unchanged**\n")
    if ch + rej == 0:
        R.append("| — | — | — | — | all phrasings unchanged |")
    open(a.report, "w").write("\n".join(R))
    print(f"-> {a.out}; report -> {a.report}")


if __name__ == "__main__":
    main()
