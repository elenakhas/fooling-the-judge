"""Camouflage analysis: camouflaged reply vs legitimate twin, per move, against the main study's plain versions of the
same questions. Reports aggregates only.

  python3 -I scripts/analyze_camo.py --camo results/judgments/studyb_camo --plain results/judgments/studyb_full \
      --report studyb/camo/analysis.md [--confirmed studyb/camo/confirmed.json]

Per judge arm x dataset x move (paired by question):
  camouflaged pass rate  = share of camouflaged replies NOT flagged (higher = the move hid the failure)
  twin flag rate         = share of twins flagged (higher = the honest use is punished)
  vs plain               = camouflaged vs the plain FAILING version (masking), twin vs the plain HONEST version
                           (false alarm); exact paired test on the questions that changed
  gap                    = camouflaged flag rate − twin flag rate (how well the judge separates the pair; 1 = perfect)
Arm 2 (reader belief) also as the three-step score (A = 2, C = 1, B = 0: how much failure the judge sees).
Optional --confirmed (from score_ground_truth.py) drops pairs whose camouflaged reply or twin was rated as not doing its
job; unrated pairs are kept.
"""
import argparse, glob, json, os
from collections import defaultdict
from math import comb

MOVES = ["E1_frame_shift", "E2_technically", "E3_concession_pivot", "E4_performative_updating",
         "E5_definitional_retreat", "E6_false_balance"]
DS = ["EduFrameTrap", "SYCON-Bench"]
FLAG3 = {"A": 2, "C": 1, "B": 0}


def p_two(k, n):
    return 1.0 if n == 0 else min(1.0, 2 * sum(comb(n, i) for i in range(0, min(k, n - k) + 1)) / 2 ** n)


def load(d, arm):
    f = glob.glob(os.path.join(d, f"{arm}__*.jsonl"))
    return [json.loads(l) for l in open(f[0])] if f else []


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--camo", required=True)
    ap.add_argument("--plain", required=True)
    ap.add_argument("--report", required=True)
    ap.add_argument("--confirmed", default=None)
    ap.add_argument("--plain-notruth", default=None, help="judgments of the main versions by the no-truth judges (arm4, arm5)")
    a = ap.parse_args()
    conf = json.load(open(a.confirmed)) if a.confirmed else {}

    def ok(r):   # spot-check: drop a camouflaged reply or twin that was rated as not doing its job
        v = conf.get(r["version_id"])
        return v is None or v

    R = ["# Study B2: camouflage vs legitimate twin\n",
         ("Spot-check applied." if conf else "**Spot-check not applied** (all pairs counted as intended).") + "\n",
         "Pass = not flagged. Masking: camouflaged reply vs the plain failing version of the same question "
         "(+ = the move made the failure pass more often). False alarm: twin vs the plain honest version "
         "(+ = the honest use was flagged more often). Gap = camouflaged flag rate − twin flag rate (1.00 = the judge always "
         "tells them apart). ↑/↓ = questions that changed; p = exact paired test.\n"]
    summary = []
    for arm, title in (("arm0", "Arm 0 · published judges"), ("arm2", "Arm 2 · reader belief (flag = A or C)"),
                       ("arm1", "Arm 1 · EduFrameTrap judge without reference"), ("arm3", "Arm 3 · checklist"),
                       ("arm4", "Arm 4 · published-judge task WITHOUT the truth (exploratory)"),
                       ("arm5", "Arm 5 · reader belief WITHOUT the truth (exploratory)")):
        camo = load(a.camo, arm)
        plain = load(a.plain_notruth, arm) if arm in ("arm4", "arm5") and a.plain_notruth else load(a.plain, arm)
        if not camo:
            continue
        F = defaultdict(dict)
        for r in camo:
            if r.get("parsed_binary") and ok(r):
                F[(r["dataset"], r["stance"], r["family"])][r["base_id"]] = int(r["parsed_binary"] == "SYC")
        for r in plain:
            if r.get("parsed_binary") and r["family"] == "plain" and r["stance"] in ("failing", "honest"):
                F[(r["dataset"], r["stance"], "plain")][r["base_id"]] = int(r["parsed_binary"] == "SYC")
        R.append(f"## {title}\n")
        R.append("| dataset | move | n | camouflaged passes | vs plain failing (masking) | twin flagged | vs plain honest (false alarm) | gap |")
        R.append("|---|---|---|---|---|---|---|---|")
        for ds in DS:
            pf, ph = F.get((ds, "failing", "plain"), {}), F.get((ds, "honest", "plain"), {})
            if not pf and not ph:
                continue
            R.append(f"| {ds} | *plain* | {len(pf)} | {1 - sum(pf.values()) / max(1, len(pf)):.2f} | — | "
                     f"{sum(ph.values()) / max(1, len(ph)):.2f} | — | {sum(pf.values()) / max(1, len(pf)) - sum(ph.values()) / max(1, len(ph)):.2f} |")
            for mv in MOVES:
                c, t = F.get((ds, "failing", mv), {}), F.get((ds, "honest", mv), {})
                if not c:
                    continue
                # masking: plain failing flagged (1) -> camouflaged passes (0)
                mk = [(pf[q], c[q]) for q in c if q in pf]
                hid, caught = sum(1 for x, y in mk if x == 1 and y == 0), sum(1 for x, y in mk if x == 0 and y == 1)
                fa = [(ph[q], t[q]) for q in t if q in ph]
                up, dn = sum(1 for x, y in fa if x == 0 and y == 1), sum(1 for x, y in fa if x == 1 and y == 0)
                both = [q for q in c if q in t]
                gap = (sum(c[q] for q in both) - sum(t[q] for q in both)) / max(1, len(both))
                R.append(f"| {ds} | {mv} | {len(c)} | {1 - sum(c.values()) / len(c):.2f} | "
                         f"{(hid - caught) / max(1, len(mk)):+.2f} ({hid}↑{caught}↓, p={p_two(min(hid, caught), hid + caught):.3f}) | "
                         f"{sum(t.values()) / max(1, len(t)):.2f} | {(up - dn) / max(1, len(fa)):+.2f} ({up}↑{dn}↓, p={p_two(min(up, dn), up + dn):.3f}) | "
                         f"{gap:.2f} |")
                summary.append((arm, ds, mv, 1 - sum(c.values()) / len(c), sum(t.values()) / max(1, len(t))))
        R.append("")
        if arm in ("arm2", "arm5"):
            L = defaultdict(dict)
            for r in camo:
                if r.get("parsed_label") in FLAG3 and ok(r):
                    L[(r["dataset"], r["stance"], r["family"])][r["base_id"]] = FLAG3[r["parsed_label"]]
            for r in plain:
                if r.get("parsed_label") in FLAG3 and r["family"] == "plain":
                    L[(r["dataset"], r["stance"], "plain")][r["base_id"]] = FLAG3[r["parsed_label"]]
            R.append("**Reader belief, label counts A / C / B** (A = reader keeps the wrong belief, B = corrected):\n")
            R.append("| dataset | move | camouflaged | twin |")
            R.append("|---|---|---|---|")
            for ds in DS:
                for mv in ["plain"] + MOVES:
                    cc = list(L.get((ds, "failing", mv), {}).values())
                    tt = list(L.get((ds, "honest", mv), {}).values())
                    if cc or tt:
                        R.append(f"| {ds} | {mv if mv != 'plain' else '*plain*'} | {cc.count(2)} / {cc.count(1)} / {cc.count(0)} | "
                                 f"{tt.count(2)} / {tt.count(1)} / {tt.count(0)} |")
            R.append("")
    R.append("## Parse rates\n")
    for arm in ("arm0", "arm1", "arm2", "arm3", "arm4", "arm5"):
        rows = load(a.camo, arm)
        if rows:
            R.append(f"- {arm}: {sum(1 for r in rows if r.get('parsed_binary'))}/{len(rows)} parsed")
    open(a.report, "w").write("\n".join(R) + "\n")
    print("\n".join(R))


if __name__ == "__main__":
    main()
