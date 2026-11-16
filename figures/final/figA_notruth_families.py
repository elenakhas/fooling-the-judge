"""Appendix figure: effect of each wording family, judges WITHOUT the truth (EduFrameTrap + SYCON, 40 questions)."""
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
COLS = [("Sonnet 5.5", "pub-noref", "Published\ntask"), ("Sonnet 5.5", "belief-noref", "Reader\nbelief"),
        ("gpt-oss-120b", "pub-noref", "Published\ntask"), ("gpt-oss-120b", "belief-noref", "Reader\nbelief")]
STANCES = [("honest", "Honest answers\n(+ = false alarm)"), ("partial", "Partial failures\n(+ = exposed, − = hidden)"),
           ("failing", "Outright failures\n(− = hidden)")]
fig, axes = plt.subplots(1, 3, figsize=(12.5, 5.0))
for c, (st, stlab) in enumerate(STANCES):
    ax = axes[c]
    M = [[H[(m, j, st, f)]["lift"] for m, j, _ in COLS] for f in FAM]
    ax.imshow(M, cmap=cmap, vmin=-15, vmax=15, aspect="auto")
    for i, f in enumerate(FAM):
        for k, (m, j, _) in enumerate(COLS):
            h = H[(m, j, st, f)]; v = h["lift"]; dark = abs(v) >= 11
            ax.text(k, i - 0.13, f"{v:+.0f}" if round(v) != 0 else "0", ha="center", va="center", fontsize=10,
                    color="white" if dark else INK, fontweight="bold" if abs(v) >= 5 else "normal")
            ax.text(k, i + 0.28, f"{h['up']}↑ {h['down']}↓", ha="center", va="center", fontsize=7,
                    color="white" if dark else INK2)
    ax.axvline(1.5, color="white", lw=4)
    ax.set_xticks(range(4)); ax.set_xticklabels([lab for *_, lab in COLS], fontsize=8.5)
    ax.set_yticks(range(len(FAM))); ax.set_yticklabels(FAM if c == 0 else [], fontsize=10)
    ax.tick_params(length=0)
    sec = ax.secondary_xaxis("top")
    sec.set_xticks([0.5, 2.5]); sec.set_xticklabels(["Claude Sonnet 5.5", "gpt-oss-120b"], fontsize=9, color=INK2, fontweight="bold")
    sec.tick_params(length=0)
    for s in list(ax.spines.values()) + list(sec.spines.values()): s.set_visible(False)
    ax.set_title(stlab, fontsize=11, fontweight="bold", color=INK, pad=26)
cax = fig.add_axes([0.925, 0.2, 0.012, 0.55])
cb = fig.colorbar(plt.cm.ScalarMappable(cmap=cmap, norm=plt.Normalize(-15, 15)), cax=cax)
cb.set_label("Change vs plain version (points of 100)\nred = more failure seen, blue = less", fontsize=8.5, color=INK2)
cb.outline.set_visible(False)
fig.subplots_adjust(left=0.09, right=0.905, top=0.8, bottom=0.1, wspace=0.07)
fig.savefig("figures/final/figureA_notruth_wording_families.png", dpi=220)
print("ok")
