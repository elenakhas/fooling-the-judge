"""Figure 3: effect of each wording family, judges WITH the truth. Change vs plain (same question & stance),
points of 100 (published: flag rate; reader belief: A=1, C=0.5, B=0). Small text: questions toward / away from failure."""
import json, matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap
D = json.load(open("figures/figdata.json"))
H = {(h["model"], h["judge"], h["stance"], h["family"]): h for h in D["heat"]}
INK, INK2 = "#0b0b0b", "#52514e"
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10})
cmap = LinearSegmentedColormap.from_list("div", ["#184f95", "#6da7ec", "#f0efec", "#f0a09f", "#a8302f"])
FAM = ["warmth", "concession", "scope", "hedge", "booster", "credibility", "persuasion", "stacked"]
COLS = [("pub+ref", "Published"), ("belief+ref", "Reader\nbelief"), ("pub+ref|JANUS", "Published"), ("belief+ref|JANUS", "Reader\nbelief")]
STANCES = [("honest", "Honest answers\n(+ = false alarm)"), ("partial", "Partial failures\n(+ = exposed, − = hidden)"),
           ("failing", "Outright failures\n(− = hidden)")]
MODELS = [("Sonnet 5.5", "Claude Sonnet 5.5"), ("gpt-oss-120b", "gpt-oss-120b")]
fig, axes = plt.subplots(2, 3, figsize=(12.5, 8.6))
for r, (m, mlab) in enumerate(MODELS):
    for c, (st, stlab) in enumerate(STANCES):
        ax = axes[r, c]
        M = [[H[(m, j, st, f)]["lift"] for j, _ in COLS] for f in FAM]
        ax.imshow(M, cmap=cmap, vmin=-15, vmax=15, aspect="auto")
        for i, f in enumerate(FAM):
            for k, (j, _) in enumerate(COLS):
                h = H[(m, j, st, f)]; v = h["lift"]
                dark = abs(v) >= 11
                ax.text(k, i - 0.13, f"{v:+.0f}" if round(v) != 0 else "0", ha="center", va="center", fontsize=10,
                        color="white" if dark else INK, fontweight="bold" if abs(v) >= 5 else "normal")
                ax.text(k, i + 0.28, f"{h['up']}↑ {h['down']}↓", ha="center", va="center", fontsize=7,
                        color="white" if dark else INK2)
        ax.axvline(1.5, color="white", lw=4)
        ax.set_xticks(range(4)); ax.set_xticklabels([lab for _, lab in COLS], fontsize=8.5)
        ax.set_yticks(range(len(FAM))); ax.set_yticklabels(FAM if c == 0 else [], fontsize=10)
        ax.tick_params(length=0)
        sec = ax.secondary_xaxis("top")
        sec.set_xticks([0.5, 2.5]); sec.set_xticklabels(["EduFrameTrap + SYCON", "JANUS"], fontsize=8.5, color=INK2)
        sec.tick_params(length=0)
        for s in list(ax.spines.values()) + list(sec.spines.values()): s.set_visible(False)
        if r == 0: ax.set_title(stlab, fontsize=11, fontweight="bold", color=INK, pad=24)
        if c == 0: ax.set_ylabel(mlab, fontsize=11.5, fontweight="bold", color=INK, labelpad=10)
cax = fig.add_axes([0.925, 0.32, 0.012, 0.36])
cb = fig.colorbar(plt.cm.ScalarMappable(cmap=cmap, norm=plt.Normalize(-15, 15)), cax=cax)
cb.set_label("Change vs plain version (points of 100)\nred = more failure seen, blue = less", fontsize=8.5, color=INK2)
cb.outline.set_visible(False)
fig.subplots_adjust(left=0.09, right=0.905, top=0.9, bottom=0.05, wspace=0.07, hspace=0.32)
fig.savefig("figures/final/figure3_wording_families.png", dpi=220)
print("ok")
