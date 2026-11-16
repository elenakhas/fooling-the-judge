"""Figure 4: camouflaged (false) replies passed, with vs without the truth, by move, judge, dataset and model."""
import json, matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
TAG = {"Sonnet": "claude-sonnet-5-5", "gpt-oss": "openai_gpt-oss-120b"}
MAIN = {("Sonnet", True): "studyb_full", ("gpt-oss", True): "studyb_full_openai_gpt-oss-120b",
        ("Sonnet", False): "studyb_notruth", ("gpt-oss", False): "studyb_notruth_openai_gpt-oss-120b"}
CAMO = {"Sonnet": "studyb_camo", "gpt-oss": "studyb_camo_openai_gpt-oss-120b"}
ARM = {("pub", True): 0, ("pub", False): 4, ("belief", True): 2, ("belief", False): 5}
MOVES = ["plain", "E1_frame_shift", "E2_technically", "E3_concession_pivot", "E4_performative_updating", "E5_definitional_retreat", "E6_false_balance"]
MLAB = ["Plain (no move)", "Frame shift", "“Technically”", "Concession pivot", "Performative updating", "Definitional retreat", "False balance"]
def flag(r, arm):
    if arm in (2, 5): return None if r["parsed_label"] not in ("A", "B", "C") else r["parsed_label"] != "B"
    return None if r["parsed_binary"] is None else r["parsed_binary"] == "SYC"
cache = {}
def load(path):
    if path not in cache: cache[path] = [json.loads(l) for l in open(path)]
    return cache[path]
def rate(model, judge, truth, ds, mv, stance):
    arm = ARM[(judge, truth)]
    rows = load(f"results/judgments/{MAIN[(model, truth)]}/arm{arm}__{TAG[model]}.jsonl") if mv == "plain" else \
           load(f"results/judgments/{CAMO[model]}/arm{arm}__{TAG[model]}.jsonl")
    fam = "plain" if mv == "plain" else mv
    v = [flag(r, arm) for r in rows if r["family"] == fam and r["dataset"] == ds and r["stance"] == stance]
    v = [x for x in v if x is not None]
    return 100 * (1 - sum(v) / len(v)) if stance == "failing" else 100 * sum(v) / len(v)
BLUE, ORANGE, INK, INK2, GRID = "#2a78d6", "#eb6834", "#0b0b0b", "#52514e", "#e6e5e0"
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10, "axes.edgecolor": GRID, "xtick.color": INK2, "ytick.color": INK2})
fig, axes = plt.subplots(2, 2, figsize=(11.5, 7.8), sharex=True, sharey=True)
twin_max = {True: 0, False: 0}
for c, (model, mlab) in enumerate([("Sonnet", "Claude Sonnet 5.5"), ("gpt-oss", "gpt-oss-120b")]):
    for r, (ds, dlab) in enumerate([("EduFrameTrap", "EduFrameTrap"), ("SYCON-Bench", "SYCON")]):
        ax = axes[r, c]
        for judge, col, off in (("pub", BLUE, 0.17), ("belief", ORANGE, -0.17)):
            for i, mv in enumerate(MOVES):
                y = len(MOVES) - 1 - i + off
                a = rate(model, judge, True, ds, mv, "failing"); b = rate(model, judge, False, ds, mv, "failing")
                for t in (True, False): twin_max[t] = max(twin_max[t], rate(model, judge, t, ds, mv, "honest"))
                ax.plot([a, b], [y, y], color=col, lw=1.6, alpha=0.45, zorder=2)
                ax.scatter(b, y, s=100, facecolor="white", edgecolor=col, linewidth=1.6, zorder=3)
                ax.scatter(a, y, s=48, color=col, zorder=4)
        ax.axhline(len(MOVES) - 1.5, color=GRID, lw=1)
        ax.set_yticks(range(len(MOVES))); ax.set_yticklabels(MLAB[::-1])
        ax.set_xlim(-3, 105); ax.grid(axis="x", color=GRID, lw=0.8); ax.set_axisbelow(True)
        for s in ("top", "right", "left"): ax.spines[s].set_visible(False)
        ax.tick_params(axis="y", length=0)
        if r == 0: ax.set_title(mlab, loc="left", fontsize=11.5, fontweight="bold", color=INK)
        ax.text(103, len(MOVES) - 0.55, dlab, ha="right", fontsize=9.5, fontweight="bold", color=INK2)
fig.supxlabel("False (camouflaged) replies passed as fine, % (20 questions per move and dataset)", fontsize=10, color=INK2, y=0.115)
fig.legend(handles=[Line2D([], [], marker="o", ls="", color=BLUE, markersize=8, label="Published judge, with truth"),
                    Line2D([], [], marker="o", ls="", markerfacecolor="white", markeredgecolor=BLUE, markeredgewidth=1.6, markersize=8, label="Published task, no truth"),
                    Line2D([], [], marker="o", ls="", color=ORANGE, markersize=8, label="Reader-belief judge, with truth"),
                    Line2D([], [], marker="o", ls="", markerfacecolor="white", markeredgecolor=ORANGE, markeredgewidth=1.6, markersize=8, label="Reader-belief judge, no truth")],
           loc="lower center", ncol=2, frameon=False, fontsize=9.5, bbox_to_anchor=(0.55, 0.0))
fig.subplots_adjust(left=0.17, right=0.98, top=0.94, bottom=0.18, wspace=0.06, hspace=0.12)
fig.savefig("figures/final/figure4_camouflage.png", dpi=220)
print("max twin flag rate: with truth", twin_max[True], "| no truth", twin_max[False])
