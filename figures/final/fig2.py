"""Figure 2: what moves verdicts. Judges WITH the truth. Three effects per judge:
failing vs honest (same wording), partial vs honest (same wording), adding one wording family (vs plain, same stance).
Verdict scored 0-1: published = flag; reader belief A=1, C=0.5, B=0. Mean absolute difference over questions (and families)."""
import json, matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
FAM = ["warmth","concession","scope","hedge","booster","credibility","persuasion","stacked"]
SEV = {"A": 1.0, "C": 0.5, "B": 0.0}
F = {("Sonnet 5.5","pub"):"results/judgments/studyb_full/arm0__claude-sonnet-5-5.jsonl",
     ("Sonnet 5.5","belief"):"results/judgments/studyb_full/arm2__claude-sonnet-5-5.jsonl",
     ("gpt-oss-120b","pub"):"results/judgments/studyb_full_openai_gpt-oss-120b/arm0__openai_gpt-oss-120b.jsonl",
     ("gpt-oss-120b","belief"):"results/judgments/studyb_full_openai_gpt-oss-120b/arm2__openai_gpt-oss-120b.jsonl",
     ("Sonnet 5.5","pub-nt"):"results/judgments/studyb_notruth/arm4__claude-sonnet-5-5.jsonl",
     ("Sonnet 5.5","belief-nt"):"results/judgments/studyb_notruth/arm5__claude-sonnet-5-5.jsonl",
     ("gpt-oss-120b","pub-nt"):"results/judgments/studyb_notruth_openai_gpt-oss-120b/arm4__openai_gpt-oss-120b.jsonl",
     ("gpt-oss-120b","belief-nt"):"results/judgments/studyb_notruth_openai_gpt-oss-120b/arm5__openai_gpt-oss-120b.jsonl"}
GROUPS = [("EduFrameTrap + SYCON (40 questions)", ("EduFrameTrap","SYCON-Bench")), ("JANUS (20 questions)", ("JANUS",))]
def effects(f, j, dss):
    S = {}
    for r in map(json.loads, open(f)):
        if r["dataset"] not in dss: continue
        s = SEV.get(r["parsed_label"]) if j.startswith("belief") else (None if r["parsed_binary"] is None else float(r["parsed_binary"] == "SYC"))
        if s is not None: S[(r["base_id"], r["stance"], r["family"])] = s
    qs = sorted({k[0] for k in S})
    def stance(a):
        d = [abs(S[(q,a,fa)] - S[(q,"honest",fa)]) for q in qs for fa in ["plain"]+FAM if (q,a,fa) in S and (q,"honest",fa) in S]
        return sum(d)/len(d)
    w = [abs(S[(q,s,fa)] - S[(q,s,"plain")]) for q in qs for s in ("honest","failing","partial") for fa in FAM if (q,s,fa) in S and (q,s,"plain") in S]
    return stance("failing"), stance("partial"), sum(w)/len(w)
BLUE, LBLUE, GREY, INK, INK2, GRID = "#2a78d6", "#86b6ef", "#a3a29c", "#0b0b0b", "#52514e", "#e6e5e0"
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10.5, "axes.edgecolor": GRID,
                     "xtick.color": INK2, "ytick.color": INK2, "axes.labelcolor": INK2})
fig, axes = plt.subplots(1, 2, figsize=(10.8, 6.2), sharey=True)
out = {}
ROWS = [  # (group index, judge key, label, y)
    (0, "pub", "Published judge", 8.2), (0, "pub-nt", "Published task, no truth", 7.3),
    (0, "belief", "Reader-belief judge", 6.2), (0, "belief-nt", "Reader-belief, no truth", 5.3),
    (1, "pub", "Published judge", 2.6), (1, "belief", "Reader-belief judge", 1.5)]
for ax, m in zip(axes, ["Sonnet 5.5", "gpt-oss-120b"]):
    for gi, j, jlab, y in ROWS:
        fe, pe, we = effects(F[(m, j)], j, GROUPS[gi][1]); out[(m, j, gi)] = (fe, pe, we)
        nt = j.endswith("-nt")
        ax.plot([we, fe], [y, y], color=GRID, lw=3, zorder=1)
        ax.scatter(we, y, s=80, color=GREY, zorder=2)
        ax.scatter(pe, y, s=80, color=LBLUE, edgecolor=BLUE, linewidth=1.2, zorder=3)
        ax.scatter(fe, y, s=80, color=BLUE, zorder=4)
        ax.text(fe + 0.025, y, f"{fe:.2f}", va="center", fontsize=9.5, color=INK)
        ax.text(pe, y - 0.48, f"{pe:.2f}", ha="center", fontsize=8.5, color=BLUE)
        ax.text(we, y + 0.28, f"{we:.2f}", ha="center", fontsize=8.5, color=INK2)
        if nt: ax.axhspan(y - 0.45, y + 0.45, color="#f6f5f2", zorder=0)
    ax.text(-0.02, 9.0, GROUPS[0][0], fontsize=9, fontweight="bold", color=INK2, ha="left")
    ax.text(-0.02, 3.3, GROUPS[1][0], fontsize=9, fontweight="bold", color=INK2, ha="left")
    ax.set_yticks([y for *_, y in ROWS]); ax.set_yticklabels([lab for _, _, lab, _ in ROWS])
    ax.set_xlim(-0.02, 1.08); ax.set_ylim(0.6, 9.4)
    ax.set_title("Claude Sonnet 5.5" if m.startswith("Sonnet") else m, loc="left", fontsize=11.5, fontweight="bold", color=INK, pad=8)
    ax.grid(axis="x", color=GRID, lw=0.8); ax.set_axisbelow(True)
    for s_ in ("top", "right", "left"): ax.spines[s_].set_visible(False)
    ax.tick_params(axis="y", length=0)
fig.supxlabel("Mean change in verdict (0 = never changes, 1 = always changes)", fontsize=10, color=INK2, y=0.1)
fig.legend(handles=[Line2D([], [], marker="o", ls="", color=BLUE, markersize=9, label="Failing vs honest (same wording)"),
                    Line2D([], [], marker="o", ls="", markerfacecolor=LBLUE, markeredgecolor=BLUE, markersize=9, label="Partial vs honest (same wording)"),
                    Line2D([], [], marker="o", ls="", color=GREY, markersize=9, label="Adding one wording family (same stance)")],
           loc="lower center", ncol=3, frameon=False, fontsize=9.5, bbox_to_anchor=(0.5, 0.0))
fig.subplots_adjust(left=0.18, right=0.98, top=0.89, bottom=0.2, wspace=0.08)
fig.savefig("figures/final/figure2_stance_vs_wording.png", dpi=220)
for k, v in out.items(): print(k, [round(x, 3) for x in v])
