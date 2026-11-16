"""Paired tests for the main study. Reports aggregates only (no question-level verdicts).

  python3 -I scripts/analyze_studyb.py --judgments results/judgments/studyb_full --report studyb/full/analysis.md \
      [--confirmed studyb/full/confirmed.json] [--rejudge results/judgments/studyb_full_rejudge]

Wording effects, per judge model: arm 0 (published judges) McNemar tests of detection lift (failing, partial) and
false-alarm lift (honest), plus arm 2 (reader belief) sign tests of the three-step label shift, each condition vs plain,
per dataset: 2 arms x 3 datasets x 8 conditions x 3 stances = 144 tests, Holm-corrected.
Partial vs failing: per question, mean partial change minus mean failing change over the 8 conditions; one-sided Wilcoxon signed-rank
(partial more negative = more masking; arm 2 oriented so that − = less failure seen), 6 tests (2 arms x 3 datasets), Holm-corrected.
Also: the same contrasts pooled over the three datasets (simple paired tests),
arms 1 and 3 (EduFrameTrap only, uncorrected), and the re-judge flip rate.
Without --confirmed every version counts at the stance it was written for.
"""
import argparse, glob, json, os
from collections import defaultdict
from math import comb

FAM = ["warmth", "concession", "scope", "hedge", "booster", "credibility", "persuasion", "stacked"]
DS = ["EduFrameTrap", "SYCON-Bench", "JANUS"]
ST = ["honest", "failing", "partial"]
SEV = {"A": 0, "C": 1, "B": 2}
FLAG3 = {"A": 2, "C": 1, "B": 0}   # analysis orientation: how much failure the judge sees (same direction as a flag)


def binom_two_sided(k, n):
    if n == 0:
        return 1.0
    return min(1.0, 2 * sum(comb(n, i) for i in range(0, min(k, n - k) + 1)) / 2 ** n)


def wilcoxon_less(d):
    """One-sided Wilcoxon signed-rank p (H1: median < 0). scipy if available, else normal approximation."""
    d = [x for x in d if x != 0]
    if not d:
        return 1.0
    try:
        from scipy.stats import wilcoxon
        return float(wilcoxon(d, alternative="less").pvalue)
    except Exception:
        import math
        ranks = sorted(range(len(d)), key=lambda i: abs(d[i]))
        r = [0.0] * len(d)
        i = 0
        while i < len(d):
            j = i
            while j + 1 < len(d) and abs(d[ranks[j + 1]]) == abs(d[ranks[i]]):
                j += 1
            for k in range(i, j + 1):
                r[ranks[k]] = (i + j) / 2 + 1
            i = j + 1
        wplus = sum(r[i] for i in range(len(d)) if d[i] > 0)
        n = len(d)
        mu, sd = n * (n + 1) / 4, math.sqrt(n * (n + 1) * (2 * n + 1) / 24)
        z = (wplus - mu) / sd
        return 0.5 * (1 + math.erf(z / math.sqrt(2)))


def holm(ps):
    """ps: list of p -> list of Holm-adjusted p."""
    order = sorted(range(len(ps)), key=lambda i: ps[i])
    adj, run = [0.0] * len(ps), 0.0
    for rank, i in enumerate(order):
        run = max(run, min(1.0, (len(ps) - rank) * ps[i]))
        adj[i] = run
    return adj


def load(path, conf):
    rows = [json.loads(l) for l in open(path) if l.strip()]
    if conf is not None:
        rows = [r for r in rows if conf.get(r["base_id"], {}).get(r["stance"], False)]
    return rows


def flags(rows):
    out = defaultdict(dict)   # (ds, stance, fam) -> {q: 0/1}
    for r in rows:
        if r.get("parsed_binary"):
            out[(r["dataset"], r["stance"], r["family"])][r["base_id"]] = int(r["parsed_binary"] == "SYC")
    return out


def labels(rows):
    out = defaultdict(dict)
    for r in rows:
        if r.get("parsed_label") in FLAG3:
            out[(r["dataset"], r["stance"], r["family"])][r["base_id"]] = FLAG3[r["parsed_label"]]
    return out


def cell_flag(F, ds_list, st, fam):
    """Pairs (plain, cond) over questions (and datasets, if pooled) -> lift, b, c, n, p."""
    pairs = []
    for ds in ds_list:
        base, cur = F.get((ds, st, "plain"), {}), F.get((ds, st, fam), {})
        pairs += [(base[q], cur[q]) for q in cur if q in base]
    if not pairs:
        return None
    up = sum(1 for a, b in pairs if a == 0 and b == 1)
    dn = sum(1 for a, b in pairs if a == 1 and b == 0)
    return {"n": len(pairs), "eff": (up - dn) / len(pairs), "up": up, "dn": dn, "p": binom_two_sided(min(up, dn), up + dn),
            "plain": sum(a for a, _ in pairs) / len(pairs), "cond": sum(b for _, b in pairs) / len(pairs)}


def cell_shift(L, ds_list, st, fam):
    d = []
    for ds in ds_list:
        base, cur = L.get((ds, st, "plain"), {}), L.get((ds, st, fam), {})
        d += [cur[q] - base[q] for q in cur if q in base]
    if not d:
        return None
    up, dn = sum(x > 0 for x in d), sum(x < 0 for x in d)
    return {"n": len(d), "eff": sum(d) / len(d), "up": up, "dn": dn, "p": binom_two_sided(min(up, dn), up + dn)}


def h1e(M, ds, kind):
    """Per question: mean change over conditions (partial) - same (failing)."""
    per = {}
    for st in ("partial", "failing"):
        base = M.get((ds, st, "plain"), {})
        for q in base:
            ch = [M[(ds, st, f)][q] - base[q] for f in FAM if q in M.get((ds, st, f), {})]
            if ch:
                per.setdefault(q, {})[st] = sum(ch) / len(ch)
    d = [v["partial"] - v["failing"] for v in per.values() if "partial" in v and "failing" in v]
    if not d:
        return None
    return {"n": len(d), "mean": sum(d) / len(d), "p": wilcoxon_less(d)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--judgments", required=True)
    ap.add_argument("--report", required=True)
    ap.add_argument("--confirmed", default=None)
    ap.add_argument("--rejudge", default=None)
    ap.add_argument("--flag-arm", default="arm0", help="yes/no judge (arm4 = published task without the truth)")
    ap.add_argument("--shift-arm", default="arm2", help="three-label judge (arm5 = reader belief without the truth)")
    a = ap.parse_args()
    conf = json.load(open(a.confirmed)) if a.confirmed else None
    files = {os.path.basename(f).split("__")[0]: f for f in glob.glob(os.path.join(a.judgments, "arm*.jsonl"))}
    R = ["# Analysis\n",
         ("Ground truth applied (`" + a.confirmed + "`)." if conf is not None else
          "Every version counts at the stance it was written for.") + "\n",
         "Effects: arm 0 = change in flag rate (condition − plain, same question and stance; + = flagged more). "
         "Arm 2 = mean change in how much failure the reader-belief judge sees (A wrong belief kept / facts minor = 2, "
         "C unclear = 1, B right belief / facts material = 0). Both arms point the same way: + = the judge sees more "
         "failure (false alarm on honest, unmasking on failing/partial), − = less (masking on failing/partial). "
         "↑/↓ = questions that moved up/down. p = exact paired test; p_Holm over the 144 wording tests.\n"]
    F0 = flags(load(files[a.flag_arm], conf)) if a.flag_arm in files else {}
    L2 = labels(load(files[a.shift_arm], conf)) if a.shift_arm in files else {}
    if (a.flag_arm, a.shift_arm) != ("arm0", "arm2"):
        R.insert(1, f"**Exploratory run:** yes/no judge = {a.flag_arm}, three-label judge = {a.shift_arm} "
                    "(Holm and the partial-vs-failing test shown for comparability).\n")
    tests = []
    for arm, M, fn in ((a.flag_arm, F0, cell_flag), (a.shift_arm, L2, cell_shift)):
        for ds in DS:
            for st in ST:
                for fam in FAM:
                    c = fn(M, [ds], st, fam)
                    if c:
                        tests.append({"arm": arm, "ds": ds, "st": st, "fam": fam, **c})
    for t, ph in zip(tests, holm([t["p"] for t in tests])):
        t["ph"] = ph
    R.append(f"## Wording effects: {len(tests)} tests\n")
    sig = [t for t in tests if t["ph"] < 0.05]
    R.append(f"**{len(sig)} survive Holm correction; {sum(t['p'] < 0.05 for t in tests)} have uncorrected p < .05.**\n")
    for arm, title in ((a.flag_arm, f"{a.flag_arm} · yes/no judge · change in flag rate"),
                       (a.shift_arm, f"{a.shift_arm} · reader belief · mean change in failure seen (A = 2, C = 1, B = 0)")):
        R.append(f"### {title}\n")
        R.append("| dataset | stance | " + " | ".join(FAM) + " |")
        R.append("|---|---|" + "---|" * len(FAM))
        for ds in DS:
            for st in ST:
                cells = []
                for fam in FAM:
                    t = next((x for x in tests if x["arm"] == arm and x["ds"] == ds and x["st"] == st and x["fam"] == fam), None)
                    if not t:
                        cells.append("—"); continue
                    mark = "**" if t["ph"] < 0.05 else ""
                    star = "*" if t["p"] < 0.05 and t["ph"] >= 0.05 else ""
                    cells.append(f"{mark}{t['eff']:+.2f}{mark}{star} ({t['up']}↑{t['dn']}↓)")
                R.append(f"| {ds} | {st} | " + " | ".join(cells) + " |")
        R.append("\n**bold** = survives Holm; * = p < .05 uncorrected only.\n")
        if arm == a.flag_arm:
            R.append(f"Plain flag rates ({arm}): " + "; ".join(
                f"{ds} {st} {sum(F0.get((ds, st, 'plain'), {}).values())}/{len(F0.get((ds, st, 'plain'), {}))}"
                for ds in DS for st in ST) + "\n")
        else:
            dist = []
            for ds in DS:
                for st in ST:
                    v = list(L2.get((ds, st, "plain"), {}).values())
                    dist.append(f"{ds} {st} A{v.count(2)}/C{v.count(1)}/B{v.count(0)}")
            R.append(f"Plain labels ({arm}): " + "; ".join(dist) + "\n")
    # partial vs failing
    R.append("## Partial vs failing: does wording hide partial failures more than outright ones?\n")
    R.append("Per question: mean change over the 8 conditions on the partial version minus the same on the failing version; "
             "negative = markers hide partials more. One-sided Wilcoxon signed-rank, Holm over 6 tests.\n")
    R.append("| arm | dataset | n | mean difference | p | p_Holm |")
    R.append("|---|---|---|---|---|---|")
    hs = [(arm, ds, h1e(M, ds, arm)) for arm, M in ((a.flag_arm, F0), (a.shift_arm, L2)) for ds in DS]
    hs = [(arm, ds, h) for arm, ds, h in hs if h]
    for (arm, ds, h), ph in zip(hs, holm([h["p"] for _, _, h in hs])):
        R.append(f"| {arm} | {ds} | {h['n']} | {h['mean']:+.3f} | {h['p']:.3f} | {ph:.3f} |")
    # pooled over datasets
    R.append("\n## Pooled over the three datasets (simple paired tests)\n")
    for arm, M, fn in ((a.flag_arm, F0, cell_flag), (a.shift_arm, L2, cell_shift)):
        R.append(f"**{arm}**\n")
        R.append("| stance | " + " | ".join(FAM) + " |")
        R.append("|---|" + "---|" * len(FAM))
        for st in ST:
            cells = []
            for fam in FAM:
                c = fn(M, DS, st, fam)
                cells.append("—" if not c else f"{c['eff']:+.2f} ({c['up']}↑{c['dn']}↓, p={c['p']:.3f})")
            R.append(f"| {st} | " + " | ".join(cells) + " |")
        R.append("")
    # arms 1 and 3
    for arm, name in (("arm1", "Arm 1 · EduFrameTrap judge without reference"), ("arm3", "Arm 3 · fixed checklist")):
        if arm not in files or (a.flag_arm, a.shift_arm) != ("arm0", "arm2"):
            continue
        F = flags(load(files[arm], conf))
        R.append(f"## Secondary: {name} (EduFrameTrap, uncorrected)\n")
        R.append("| stance | plain flag rate | " + " | ".join(FAM) + " |")
        R.append("|---|---|" + "---|" * len(FAM))
        for st in ST:
            base = F.get(("EduFrameTrap", st, "plain"), {})
            cells = []
            for fam in FAM:
                c = cell_flag(F, ["EduFrameTrap"], st, fam)
                cells.append("—" if not c else f"{c['eff']:+.2f} ({c['up']}↑{c['dn']}↓{', p=%.3f' % c['p'] if c['p'] < 0.1 else ''})")
            R.append(f"| {st} | {sum(base.values())}/{len(base)} | " + " | ".join(cells) + " |")
        R.append("")
    # parse rates and noise
    R.append("## Parse rates and noise\n")
    for arm, fn in sorted(files.items()):
        rows = [json.loads(l) for l in open(fn)]
        miss = sum(1 for r in rows if not r.get("parsed_binary"))
        R.append(f"- {arm}: {len(rows) - miss}/{len(rows)} parsed ({miss / len(rows):.1%} missing)")
    if a.rejudge:
        R.append("")
        for arm, fn in sorted(files.items()):
            rj = os.path.join(a.rejudge, os.path.basename(fn))
            if not os.path.exists(rj):
                continue
            A = {json.loads(l)["version_id"]: json.loads(l) for l in open(fn)}
            B = {json.loads(l)["version_id"]: json.loads(l) for l in open(rj)}
            both = [v for v in B if v in A and A[v].get("parsed_binary") and B[v].get("parsed_binary")]
            fb = sum(A[v]["parsed_binary"] != B[v]["parsed_binary"] for v in both)
            fl = sum(A[v]["parsed_label"] != B[v]["parsed_label"] for v in both)
            R.append(f"- re-judge {arm}: verdict flips {fb}/{len(both)} ({fb / max(1, len(both)):.1%}), label flips {fl}/{len(both)}")
    open(a.report, "w").write("\n".join(R) + "\n")
    print("\n".join(R))


if __name__ == "__main__":
    main()
