"""Appendix tables A1 (plain detection) and A2 (verdict changes vs re-judge baseline), written as markdown."""
import json
SEV = {"A": 2, "C": 1, "B": 0}
J = {("Claude Sonnet 5.5", "Published, truth"): ("studyb_full", 0), ("Claude Sonnet 5.5", "Reader belief, truth"): ("studyb_full", 2),
     ("Claude Sonnet 5.5", "Published, no truth"): ("studyb_notruth", 4), ("Claude Sonnet 5.5", "Reader belief, no truth"): ("studyb_notruth", 5),
     ("gpt-oss-120b", "Published, truth"): ("studyb_full_openai_gpt-oss-120b", 0), ("gpt-oss-120b", "Reader belief, truth"): ("studyb_full_openai_gpt-oss-120b", 2),
     ("gpt-oss-120b", "Published, no truth"): ("studyb_notruth_openai_gpt-oss-120b", 4), ("gpt-oss-120b", "Reader belief, no truth"): ("studyb_notruth_openai_gpt-oss-120b", 5)}
TAG = {"Claude Sonnet 5.5": "claude-sonnet-5-5", "gpt-oss-120b": "openai_gpt-oss-120b"}
RJ = {"Claude Sonnet 5.5": "studyb_full_rejudge", "gpt-oss-120b": "studyb_full_rejudge_openai_gpt-oss-120b"}
DS = [("EduFrameTrap", "EduFrameTrap"), ("SYCON-Bench", "SYCON"), ("JANUS", "JANUS")]
def path(d, arm, m): return f"results/judgments/{d}/arm{arm}__{TAG[m]}.jsonl"
def flag(r, arm): return (r["parsed_label"] in ("A", "C")) if arm in (2, 5) else (r["parsed_binary"] == "SYC")
def score(r, arm):
    if arm in (2, 5): return SEV.get(r["parsed_label"])
    return None if r["parsed_binary"] is None else int(r["parsed_binary"] == "SYC")
L = ["# Appendix tables", "",
     "**Table A1. Plain versions flagged, by stance (out of 20 questions per dataset).** Published judge: flagged as failing. "
     "Reader-belief judge: labelled A (wrong belief kept / facts minor) or C (unclear); A / C / B counts in brackets. "
     "No-truth judges ran on EduFrameTrap and SYCON only. Stances are as constructed.", "",
     "| Model | Judge | Dataset | Honest | Partial | Failing |", "|---|---|---|---|---|---|"]
for (m, j), (d, arm) in J.items():
    rows = [json.loads(l) for l in open(path(d, arm, m))]
    for ds, dl in DS:
        cell = []
        for st in ("honest", "partial", "failing"):
            rr = [r for r in rows if r["dataset"] == ds and r["family"] == "plain" and r["stance"] == st]
            if not rr: cell = None; break
            n = sum(flag(r, arm) for r in rr)
            if arm in (2, 5):
                a, c, b = (sum(r["parsed_label"] == x for r in rr) for x in "ACB")
                cell.append(f"{n} ({a} / {c} / {b})")
            else: cell.append(str(n))
        if cell: L.append(f"| {m} | {j} | {dl} | {cell[0]} | {cell[1]} | {cell[2]} |")
L += ["", "**Table A2. Verdicts changed by added wording, compared with re-judging identical text.** "
      "A verdict changed when a version with one wording family was judged differently from the plain version of the same answer "
      "(reader belief: any change among A, C, B). Toward = more failure seen; away = less. Re-judge: a stratified 10% sample judged twice "
      "with identical text (judges with the truth only). Cells show the % of versions whose verdict changed, then the % that changed toward / away; "
      "toward and away add up to the total, give or take rounding. Denominators: 480 versions per stance with truth (60 questions × 8 families), 320 without truth "
      "(40 questions), and 54 per stance in the re-judge sample; a few versions are missing because the judge's output could not be parsed "
      "(at most 8 per cell).", "",
      "| Model | Judge | Honest: % changed (toward / away) | Partial | Failing | All | Re-judge, identical text: honest / partial / failing |",
      "|---|---|---|---|---|---|---|"]
for (m, j), (d, arm) in J.items():
    S = {}
    for r in map(json.loads, open(path(d, arm, m))):
        s = score(r, arm)
        if s is not None: S[(r["base_id"], r["stance"], r["family"])] = s
    cells, tot = [], [0, 0, 0, 0]
    for st in ("honest", "partial", "failing"):
        n = ch = up = dn = 0
        for (q, s_, fa), v in S.items():
            if s_ != st or fa == "plain" or (q, st, "plain") not in S: continue
            p = S[(q, st, "plain")]; n += 1
            if v != p: ch += 1; up += v > p; dn += v < p
        cells.append(f"{100*ch/n:.1f}% ({100*up/n:.1f} / {100*dn/n:.1f})")
        for i, x in enumerate((n, ch, up, dn)): tot[i] += x
    rj = "—"
    if arm in (0, 2):
        M = {r["version_id"]: score(r, arm) for r in map(json.loads, open(path(d, arm, m)))}
        c = {"honest": [0, 0], "partial": [0, 0], "failing": [0, 0]}
        for r in map(json.loads, open(path(RJ[m], arm, m))):
            a, b = score(r, arm), M.get(r["version_id"])
            if a is None or b is None: continue
            c[r["stance"]][0] += 1; c[r["stance"]][1] += a != b
        rj = " / ".join(f"{100*c[s][1]/c[s][0]:.1f}" for s in ("honest", "partial", "failing")) + "%"
    L.append(f"| {m} | {j} | {cells[0]} | {cells[1]} | {cells[2]} | {100*tot[1]/tot[0]:.1f}% | {rj} |")
open("figures/final/appendix_tables_A1_A2.md", "w").write("\n".join(L) + "\n")
print("\n".join(L))
