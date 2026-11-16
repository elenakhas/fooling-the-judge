"""Figure A2: when added wording changes a verdict, how often does the judge's rationale cite that wording?"""
import json, matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
D = json.load(open("figures/figdata.json"))
T = {(t["model"], t["judge"], t["stance"]): t for t in D["traces"]}
BLUE, ORANGE, INK, INK2, GRID = "#2a78d6", "#eb6834", "#0b0b0b", "#52514e", "#e6e5e0"
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10.5, "axes.edgecolor": GRID, "xtick.color": INK2, "ytick.color": INK2, "axes.labelcolor": INK2})
JUDGES = [("pub+ref", "Published judge\nwith truth"), ("belief+ref", "Reader-belief judge\nwith truth"),
          ("pub-noref", "Published task\nno truth"), ("belief-noref", "Reader-belief judge\nno truth")]
fig, ax = plt.subplots(figsize=(9.2, 4.3))
w = 0.36
for k, (m, col) in enumerate([("Sonnet 5.5", BLUE), ("gpt-oss-120b", ORANGE)]):
    for i, (j, _) in enumerate(JUDGES):
        t = T[(m, j, "all")]
        v = 100 * t["cited_changed"] / t["n_changed"] if t["n_changed"] else 0
        x = i + (k - 0.5) * w
        ax.bar(x, v, width=w * 0.9, color=col, zorder=2)
        ax.text(x, v + 1.0, f"{t['cited_changed']}/{t['n_changed']}", ha="center", fontsize=9, color=INK)
        ax.plot([x - w * 0.42, x + w * 0.42], [100 * t["cited_all"]] * 2, color=INK, lw=1.5, zorder=3)
ax.set_xticks(range(4)); ax.set_xticklabels([lab for _, lab in JUDGES], fontsize=9.5)
ax.set_ylabel("Verdict changes whose rationale\ncites the added wording (%)")
ax.set_ylim(0, 32); ax.grid(axis="y", color=GRID, lw=0.8); ax.set_axisbelow(True)
for s in ("top", "right"): ax.spines[s].set_visible(False)
ax.tick_params(axis="x", length=0)
ax.legend(handles=[plt.Rectangle((0, 0), 1, 1, color=BLUE, label="Claude Sonnet 5.5"),
                   plt.Rectangle((0, 0), 1, 1, color=ORANGE, label="gpt-oss-120b"),
                   Line2D([], [], color=INK, lw=1.5, label="Rate over all versions with added wording")],
          frameon=False, fontsize=9, loc="upper right")
fig.subplots_adjust(left=0.12, right=0.98, top=0.95, bottom=0.17)
fig.savefig("figures/final/figureA2_traces.png", dpi=220)
print("ok")
