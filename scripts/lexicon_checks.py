"""Lexicon checks for the versions, using the open published lexicons built by fetch_lexicons.py (in $FTJ_DATA/lexicons)
plus ConvoKit politeness strategies, Empath and VADER (see features_open.py for sources).

  python3 -I scripts/lexicon_checks.py --items studyb/items_60.jsonl --ingredients studyb/full/ingredients.jsonl \
      --versions studyb/full/versions.jsonl --report studyb/full/lexicon_checks.md --csv studyb/full/lexicon_features.csv

Three checks:
  1. Ingredients: no family vocabulary in the content sentences, using the full lexicon categories (the prompt's short
     ban list is all a model can follow; this checks against the published lists).
  2. Plain versions: no family markers; plain honest and plain failing should not differ on style dimensions.
  3. Manipulation check: each family, compared with plain for the same question, clarity and stance, should rise on its
     own target dimension and stay flat on the others.

Levels: ERROR = family vocabulary where it must not be; WARN = worth a look (hedge words are often content, e.g.
"approximately" in chemistry); INFO = descriptive. Scope shifting has NO published lexicon; it is checked against the
frame wording only (assemble_versions.py), and this script says so rather than inventing a list.
Use --no-tools to skip ConvoKit/Empath/VADER (faster; warmth is then measured by the opinion lexicon only).
"""
import argparse, csv, json, os, sys
from collections import defaultdict
from statistics import mean

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import features_open as FO
from prompts_ingredients import FIELDS

# term-level categories: name -> (lexicon files, source)
TERM_CATS = {
    "concession_connective": (["dimlex_comparison"], "DiMLex-Eng connectives whose dominant sense is Comparison (concession, contrast; includes though/although/still/yet)"),
    "hedge": (["politeness_hedges"], "politeness package hedge list (Yeomans et al. 2018)"),
    "weakener": (["ember_weakeners", "zhou_weakeners"], "EMBER + Zhou et al. 2023 weakeners"),
    "strengthener": (["ember_strengtheners", "zhou_strengtheners"], "EMBER + Zhou et al. 2023 strengtheners"),
    "opinion_pos": (["opinion_positive"], "Hu & Liu 2004 positive opinion words"),
    "opinion_neg": (["opinion_negative"], "Hu & Liu 2004 negative opinion words"),
}
AMBIGUOUS = {"still", "yet", "while", "instead of", "by the way", "as though", "much as"}   # often temporal/literal, not contrast
OPINION_STOP = {"like"}   # Hu & Liu counts the preposition ("points like these") as positive; known false hit
# tool-based dimensions (counts per text), grouped
WARMTH_TOOLS = ["ck_gratitude", "ck_greeting", "ck_apologizing", "ck_please", "ck_deference",
                "empath_politeness", "empath_positive_emotion", "empath_affection"]
DIMENSIONS = {   # dimension -> list of features summed
    "warmth": ["opinion_pos"] + WARMTH_TOOLS,
    "concession": ["concession_connective"],
    "hedging": ["hedge", "weakener", "ck_hedges"],
    "certainty": ["strengthener", "ck_factuality"],
    "negativity": ["opinion_neg"],
}
TARGET = {"warmth": ["warmth"], "concession": ["concession"], "scope": [], "hedge": ["hedging"],
          "booster": ["certainty"], "credibility": [], "persuasion": [], "stacked": ["warmth", "concession"]}
NO_LEXICON = {"scope": "no published lexicon for scope shifting",
              "credibility": "no published lexicon for credibility cues (Zhou evidential strengtheners count as certainty)",
              "persuasion": "no published lexicon for reader-directed persuasion (majority, consistency, identity)"}


def regex_for(files):
    return FO._phrase_regex(sum((FO._load(n) for n in files), []))


RX = {c: regex_for(files) for c, (files, _) in TERM_CATS.items() if c not in ("opinion_pos", "opinion_neg")}
WORDS = {c: set(sum((FO._load(n) for n in files), [])) for c, (files, _) in TERM_CATS.items() if c.startswith("opinion")}


def terms(text):
    """Matched terms per term category."""
    t = (text or "").replace("’", "'")
    out = {c: [m.lower() for m in rx.findall(t)] if rx else [] for c, rx in RX.items()}
    toks = FO._TOKEN.findall(t.lower())
    for c, ws in WORDS.items():
        out[c] = [w for w in toks if w in ws and w not in OPINION_STOP]
    return out


def features(text, tools):
    tm = terms(text)
    f = {c: len(v) for c, v in tm.items()}
    f["n_words"] = len(FO._TOKEN.findall((text or "").lower()))
    if tools:
        o = FO.open_features(text, tools=True)
        for k in WARMTH_TOOLS + ["ck_hedges", "ck_factuality", "vader_compound"]:
            f[k] = o.get(k) or 0
    for d, parts in DIMENSIONS.items():
        f["dim_" + d] = sum(f.get(p, 0) or 0 for p in parts)
    return f, tm


def check_ingredients(items, rows, tools, R):
    R.append("## 1. Ingredients\n")
    n_err = n_warn = 0
    for r in rows:
        ing, issues = r.get("ingredients") or {}, []
        pair = {}
        for k in FIELDS.get(r["source"], []):
            v = ing.get(k)
            if k == "notes" or not v:
                continue
            f, tm = features(v, tools)
            pair[k] = f
            hard = [w for w in tm["concession_connective"] if w not in AMBIGUOUS]
            soft = [w for w in tm["concession_connective"] if w in AMBIGUOUS]
            if hard:
                issues.append(("ERROR", f"{k}: concession/contrast connectives {hard}"))
            if soft:
                issues.append(("WARN", f"{k}: possibly contrastive {soft} (check whether temporal/literal)"))
            for c in ("weakener", "strengthener"):
                if tm[c]:
                    issues.append(("ERROR", f"{k}: epistemic {c}s {tm[c]}"))
            if tm["hedge"]:
                issues.append(("WARN", f"{k}: hedge words {tm['hedge']} (fine if they are content, e.g. 'approximately')"))
            if tools:
                w = {t: f[t] for t in ("ck_gratitude", "ck_greeting", "ck_apologizing", "ck_please") if f.get(t)}
                if w:
                    issues.append(("ERROR", f"{k}: politeness strategies {w}"))
            if tm["opinion_pos"] or tm["opinion_neg"]:
                issues.append(("INFO", f"{k}: opinion words +{tm['opinion_pos']} −{tm['opinion_neg']}"))
        # honest/failing pairs should not differ in style
        for a, b in (("honest_core", "failing_core"), ("honest_core", "partial_core"),
                     ("adverse_honest", "adverse_downplayed"), ("adverse_honest", "adverse_partial")):
            if a in pair and b in pair:
                diffs = {d: pair[b]["dim_" + d] - pair[a]["dim_" + d] for d in DIMENSIONS
                         if pair[b]["dim_" + d] != pair[a]["dim_" + d]}
                if diffs:
                    lvl = "WARN" if any(abs(x) >= 2 for x in diffs.values()) else "INFO"
                    issues.append((lvl, f"style difference {b} − {a}: {diffs}"))
        n_err += sum(s == "ERROR" for s, _ in issues)
        n_warn += sum(s == "WARN" for s, _ in issues)
        R.append(f"### {r['base_id']} ({r['source']})\n")
        R += [f"- **{s}** {m}" if s != "INFO" else f"- {s} {m}" for s, m in issues] or ["- no lexicon hits"]
        R.append("")
    return n_err, n_warn


def pool_coverage(frames, R):
    """For every phrasing in every marker pool: which lexicon dimensions recognise it (lexicon terms only, no tools)."""
    R.append("\n## 4. Marker pools: which phrasings the lexicons recognise\n")
    R.append("Share of phrasings with at least one hit on the family's target dimension, and the phrasings with none. "
             "Unrecognised phrasings are not wrong; they show where the published lexicons stop.\n")
    R.append("| family | pool | phrasings | recognised on target | not recognised |")
    R.append("|---|---|---|---|---|")
    for fam, by_ds in frames["pools"].items():
        tgt = TARGET.get(fam, [])
        for ds, pool in by_ds.items():
            if isinstance(pool, str):
                continue
            hits, miss = 0, []
            for ph in pool:
                f, _ = features(ph.replace("{reframe}", "the long term"), tools=False)
                if tgt and any(f["dim_" + t] > 0 for t in tgt):
                    hits += 1
                else:
                    miss.append(ph)
            shown = "; ".join(miss[:6]) + (f" … (+{len(miss) - 6})" if len(miss) > 6 else "")
            R.append(f"| {fam} | {ds} | {len(pool)} | " + (f"{hits}/{len(pool)}" if tgt else "no lexicon") +
                     f" | {shown if tgt else '—'} |")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--items", required=True)
    ap.add_argument("--ingredients", required=True)
    ap.add_argument("--versions", required=True)
    ap.add_argument("--report", required=True)
    ap.add_argument("--csv", required=True)
    ap.add_argument("--no-tools", action="store_true")
    ap.add_argument("--frames", default=None, help="also report which lexicons recognise each phrasing in the marker pools")
    a = ap.parse_args()
    tools = not a.no_tools
    status = FO.lexicon_status()
    missing = [k for k, v in status.items() if not v]
    if not any(status.values()):
        sys.exit(f"No lexicons found in {FO.LEX}. Run fetch_lexicons.py or set FTJ_DATA.")
    items = {json.loads(l)["base_id"]: json.loads(l) for l in open(a.items)}
    ing_rows = [json.loads(l) for l in open(a.ingredients)]
    vers = [json.loads(l) for l in open(a.versions)]

    R = ["# Lexicon checks\n",
         f"Lexicons from `{FO.LEX}`" + (f" (missing: {', '.join(missing)})" if missing else "") +
         ("; ConvoKit, Empath and VADER used." if tools else "; tools skipped (--no-tools)."),
         "Scope shifting has no published lexicon, so it is not measured here (only the frame-wording check in assembly).\n",
         "Dimensions: " + "; ".join(f"**{d}** = {' + '.join(p)}" for d, p in DIMENSIONS.items()) + "\n"]
    n_err, n_warn = check_ingredients(items, ing_rows, tools, R)

    # per-version features
    F = {}
    for v in vers:
        f, tm = features(v["t2"], tools)
        F[v["version_id"]] = (v, f, tm)
    with open(a.csv, "w", newline="") as fh:
        cols = ["version_id", "base_id", "dataset", "clarity", "stance", "family"] + \
               sorted({k for _, f, _ in F.values() for k in f})
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        for v, f, _ in F.values():
            w.writerow({**{k: v.get(k) for k in cols[:6]}, **f})

    # 2. plain versions
    R.append("## 2. Plain versions\n")
    plain_issues = []
    for v, f, tm in F.values():
        if v["family"] != "plain":
            continue
        hard = [x for x in tm["concession_connective"] if x not in AMBIGUOUS]
        if hard:
            plain_issues.append(("ERROR", f"{v['version_id']}: concession/contrast connectives {hard}"))
        if tools and any(f.get(t) for t in ("ck_gratitude", "ck_greeting", "ck_apologizing", "ck_please")):
            plain_issues.append(("ERROR", f"{v['version_id']}: politeness strategies"))
        if tm["weakener"] or tm["strengthener"]:
            plain_issues.append(("ERROR", f"{v['version_id']}: epistemic markers {tm['weakener'] + tm['strengthener']}"))
    n_err += sum(s == "ERROR" for s, _ in plain_issues)
    R += [f"- **{s}** {m}" for s, m in plain_issues] or ["- no family markers in any plain version"]
    R.append("\nPlain failing/partial − plain honest, per question (style should not differ; content differences can "
             "move opinion words a little):\n")
    R.append("| base_id | clarity | stance | " + " | ".join(DIMENSIONS) + " |")
    R.append("|---|---|---|" + "---|" * len(DIMENSIONS))
    idx = {(v["base_id"], v.get("clarity", "explicit"), v["stance"], v["family"]): f for v, f, _ in F.values()}
    for (bid, cl, st, fam), f in sorted(idx.items()):
        if st == "honest" and fam == "plain":
            for other in ("failing", "partial"):
                if (bid, cl, other, "plain") in idx:
                    g = idx[(bid, cl, other, "plain")]
                    R.append(f"| {bid} | {cl} | {other} | " +
                             " | ".join(f"{g['dim_'+d] - f['dim_'+d]:+d}" for d in DIMENSIONS) + " |")

    # 3. manipulation check
    R.append("\n## 3. Manipulation check (condition − plain, same question and stance)\n")
    R.append("Mean change in counts; in brackets the share of pairs where the dimension went up. The family's target "
             "dimension should go up in every pair; the others should stay near 0.\n")
    R.append("| family | target | n pairs | " + " | ".join(DIMENSIONS) + " | verdict |")
    R.append("|---|---|---|" + "---|" * len(DIMENSIONS) + "---|")
    for fam in ("warmth", "concession", "scope", "hedge", "booster", "credibility", "persuasion", "stacked"):
        diffs = defaultdict(list)
        for (bid, cl, st, fm), f in idx.items():
            if fm == fam and (bid, cl, st, "plain") in idx:
                p = idx[(bid, cl, st, "plain")]
                for d in DIMENSIONS:
                    diffs[d].append(f["dim_" + d] - p["dim_" + d])
        if not diffs:
            continue
        n = len(diffs["warmth"])
        cells = [f"{mean(diffs[d]):+.2f} ({sum(x > 0 for x in diffs[d])/n:.0%})" for d in DIMENSIONS]
        tgt = TARGET[fam]
        off = [d for d in DIMENSIONS if d not in tgt and abs(mean(diffs[d])) >= 0.5]
        if tgt:
            missed = [t for t in tgt if not all(x > 0 for x in diffs[t])]
            verdict = ("OK" if not missed and not off else
                       (f"{missed} not raised in every pair; " if missed else "") + (f"off-target: {off}" if off else ""))
        else:
            verdict = NO_LEXICON[fam] + (f"; off-target: {off}" if off else "; no off-target change")
        R.append(f"| {fam} | {', '.join(tgt) or '—'} | {n} | " + " | ".join(cells) + f" | {verdict} |")
    # which frame words drive each dimension (so cross-loading is visible)
    R.append("\nFrame words picked up by the lexicons (terms present in a family version but not in its plain twin):\n")
    for fam in ("warmth", "concession", "scope", "hedge", "booster", "credibility", "persuasion", "stacked"):
        extra = defaultdict(set)
        for (bid, cl, st, fm) in idx:
            if fm != fam or (bid, cl, st, "plain") not in idx:
                continue
            tv = next(tm for v, _, tm in F.values() if (v["base_id"], v.get("clarity", "explicit"), v["stance"], v["family"]) == (bid, cl, st, fm))
            tp = next(tm for v, _, tm in F.values() if (v["base_id"], v.get("clarity", "explicit"), v["stance"], v["family"]) == (bid, cl, st, "plain"))
            for c in tv:
                for t in set(tv[c]) - set(tp[c]):
                    extra[c].add(t)
        R.append(f"- **{fam}**: " + ("; ".join(f"{c}: {sorted(ts)}" for c, ts in sorted(extra.items())) or "none"))
    if a.frames:
        pool_coverage(json.load(open(a.frames)), R)
    R.insert(1, f"**{len(ing_rows)} ingredient sets, {len(vers)} versions · {n_err} errors · {n_warn} warnings**\n")
    os.makedirs(os.path.dirname(os.path.abspath(a.report)), exist_ok=True)
    open(a.report, "w").write("\n".join(R))
    print(f"{n_err} errors, {n_warn} warnings -> {a.report}; features -> {a.csv}")


if __name__ == "__main__":
    main()
