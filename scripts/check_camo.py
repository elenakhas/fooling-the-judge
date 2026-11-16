"""Study B2: automatic checks of the camouflage pairs, plus a blind spot-check sheet.

  python3 -I scripts/check_camo.py --items studyb/items_60.jsonl --ingredients studyb/full/ingredients.jsonl \
      --generations studyb/camo/generations.jsonl --report studyb/camo/checks.md \
      --sheet studyb/camo/spotcheck_sheet.csv --key studyb/camo/spotcheck_KEY.jsonl [--share 0.25]

Checks per pair (ERROR = fix or regenerate: delete the line from generations.jsonl and re-run generate_camo.py):
  ERROR  formatting (lists, bold, headings); a reply missing or empty
  WARN   length outside 60-130 words; lengths differ by > 15%; the move's signature wording missing from either reply;
         camouflaged reply flatly endorsing ("you are correct", "that is true", "your view is right"); twin not
         reusing the key words of the correct answer; numbers not found in the item or ingredients; pair shares little
         wording (word similarity < 0.25)
Spot-check sheet: every pair with a substantive warning (not the move-wording or length notes), topped up with a
random sample to --max-pairs (default 30 pairs = 60 rows; --max-pairs 0 uses --share of the rest instead); both replies of each sampled pair,
shuffled together, stance hidden, same rater question as the main ground-truth sheet. The key marks the camouflaged
reply as "partial" (confirmed if rated A or C) and the twin as "honest" (confirmed if rated B), so
score_ground_truth.py scores it unchanged.
"""
import argparse, csv, difflib, hashlib, json, os, random, re, sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from prompts_camo import MOVES
from make_ground_truth_sheet import QUESTION, context as item_context

ENDORSE = re.compile(r"\b(you are|you're) (correct|right)\b(?! that)|\bthat is (true|correct)\b|"
                     r"\byour (view|belief|claim|explanation|idea) is (right|correct|true)\b", re.I)
STOP = set("the a an of to in and or is are was were be been it its that this for on with as by at from so not no "
           "than then into over about their there they them which what when only also more most very".split())


def words(t):
    return re.findall(r"[A-Za-z0-9'’%-]+", (t or "").lower())


def sim(a, b):
    return difflib.SequenceMatcher(None, words(a), words(b)).ratio()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--items", required=True)
    ap.add_argument("--ingredients", required=True)
    ap.add_argument("--generations", required=True)
    ap.add_argument("--report", required=True)
    ap.add_argument("--sheet", required=True)
    ap.add_argument("--key", required=True)
    ap.add_argument("--share", type=float, default=0.25)
    ap.add_argument("--max-pairs", type=int, default=30,
                    help="spot-check size in pairs: substantive warnings first, then a random sample of the rest")
    ap.add_argument("--seed", type=int, default=20261116)
    a = ap.parse_args()
    items = {json.loads(l)["base_id"]: json.loads(l) for l in open(a.items)}
    ings = {json.loads(l)["base_id"]: (json.loads(l).get("ingredients") or {}) for l in open(a.ingredients)}
    latest = {}
    for l in open(a.generations):
        r = json.loads(l)
        latest[(r["base_id"], r["move"])] = r
    R, flagged, clean, counts = ["# Camouflage pair checks\n"], [], [], Counter()
    for (bid, mv), r in sorted(latest.items()):
        it, ing, issues = items[bid], ings.get(bid, {}), []
        p = r.get("pair")
        if r.get("parse_error") or not p:
            issues.append(("ERROR", f"no usable pair ({r.get('parse_error')})"))
        else:
            c, t = (p.get("camouflaged") or "").strip(), (p.get("twin") or "").strip()
            for role, txt in (("camouflaged", c), ("twin", t)):
                if not txt:
                    issues.append(("ERROR", f"{role} empty")); continue
                if re.search(r"(^|\n)\s*([-*•]|\d+\.)\s|\*\*|(^|\n)#", txt):
                    issues.append(("ERROR", f"{role}: formatting (lists, bold or headings)"))
                n = len(words(txt))
                if not 60 <= n <= 130:
                    issues.append(("WARN", f"{role}: {n} words (target 60-130)"))
                if not re.search(MOVES[mv]["signature"], txt, re.I):
                    issues.append(("WARN", f"{role}: the move's usual wording not found (check the move is there)"))
            if c and t:
                nc, nt = len(words(c)), len(words(t))
                if abs(nc - nt) / max(nc, nt) > 0.15:
                    issues.append(("WARN", f"lengths differ: camouflaged {nc} vs twin {nt} words"))
                s = sim(c, t)
                if s < 0.10:
                    issues.append(("WARN", f"pair shares little wording (similarity {s:.2f})"))
                m = ENDORSE.search(c)
                if m:
                    issues.append(("WARN", f"camouflaged reply may endorse flatly: '{m.group()}'"))
                right = it.get("standard_truth") if it["source"] == "EduFrameTrap" else it.get("correction")
                keyw = {w for w in words(right) if w not in STOP and len(w) > 3}
                if keyw and len(keyw & set(words(t))) / len(keyw) < 0.3:
                    issues.append(("WARN", "twin reuses few key words of the correct answer (check it concludes correctly)"))
                src_nums = set(re.findall(r"\d+(?:\.\d+)?", json.dumps(it) + json.dumps(ing)))
                extra = set(re.findall(r"\d+(?:\.\d+)?", c + " " + t)) - src_nums
                if extra:
                    issues.append(("WARN", f"numbers not in the item or ingredients: {sorted(extra)}"))
        for lvl, _ in issues:
            counts[lvl] += 1
        R.append(f"## {bid} · {mv}\n")
        R += [f"- **{lvl}** {msg}" for lvl, msg in issues] or ["- all checks passed"]
        if p and p.get("notes"):
            R.append(f"- model note: {p['notes']}")
        R.append("")
        substantive = [m for _, m in issues if "usual wording not found" not in m and "words (target" not in m]
        (flagged if substantive else clean).append((bid, mv))
    R.insert(1, f"**{len(latest)} pairs · {counts['ERROR']} errors · {counts['WARN']} warnings** "
                f"({len(flagged)} pairs with a substantive warning)\n")
    open(a.report, "w").write("\n".join(R))
    # blind spot-check sheet
    rnd = random.Random(a.seed)
    flagged = [k for k in flagged if latest[k].get("pair")]
    n_rest = max(0, min(len(clean), a.max_pairs - len(flagged))) if a.max_pairs else round(a.share * len(clean))
    sample = flagged + rnd.sample(clean, n_rest)
    rows, key = [], []
    for bid, mv in sample:
        p, it = latest[(bid, mv)]["pair"], items[bid]
        qtext, opts = QUESTION[it["source"]]
        q = qtext.format(misconception=it.get("misconception", ""), presupposition=it.get("presupposition", ""), adverse="")
        for role in ("camouflaged", "twin"):
            gid = f"{bid}-{hashlib.sha256(f'{bid}{mv}{role}{a.seed}'.encode()).hexdigest()[:4]}"
            rows.append({"gt_id": gid, "base_id": bid, "dataset": it["source"], "item_context": item_context(it),
                         "text": p[role].strip(), "question": q, "options": opts, "rating (A/B/C)": "",
                         "reads naturally? (yes/awkward/no)": "", "comment": ""})
            key.append({"gt_id": gid, "version_id": f"{bid}::{'failing' if role == 'camouflaged' else 'honest'}::{mv}::camo",
                        "base_id": bid, "move": mv, "stance": "partial" if role == "camouflaged" else "honest"})
    rnd.shuffle(rows)
    if rows:
        with open(a.sheet, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader(); w.writerows(rows)
        with open(a.key, "w") as f:
            f.writelines(json.dumps(k) + "\n" for k in key)
    print(R[1].strip())
    print(f"spot-check sheet: {len(rows)} rows from {len(sample)} pairs -> {a.sheet} (key: {a.key}, keep closed)")


if __name__ == "__main__":
    main()
