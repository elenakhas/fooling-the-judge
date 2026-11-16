"""Extend the 40 Study B base items to the 20/20/20 design (step 4d). Keeps every existing item unchanged.

  python3 -I scripts/extend_items.py --base studyb/base_items.jsonl \
      --sycon "$FTJ_DATA/repos/SYCON-Bench/false-presuppositions-setting/data" \
      --janus "$FTJ_DATA/repos/Janus/data/janus.csv" --out studyb/items_candidates.jsonl

Adds
  SYCON: 15 new candidates drawn at random (seed 20261114) from the false-presupposition questions not yet used,
         ranked. After the ingredient run, finalize_items.py keeps the first 10 (in rank order) whose ingredients
         have a genuine kernel of truth (non-null kernel_clause), as the spec requires; the rest are dropped. The
         10 existing SYCON items are kept whatever their kernel. Note for the paper: the added 10 are screened,
         not a random sample.
  JANUS: 10 new scenarios so that all 8 domains have 2-3 items (20 in total): +2 each for Business, Finance,
         Healthcare and Law; +1 each for Media and Public Policy (Education and Workplace already have 2).
Output: 20 EduFrameTrap + 10 + 15 SYCON + 20 JANUS = 65 candidate items; new rows carry "added": "v0.5d".
"""
import argparse, csv, json, os, random
from collections import Counter, defaultdict

JANUS_TARGET = {"Business / Corporate": 3, "Finance": 3, "Healthcare": 3, "Law": 3, "Media / Information": 2,
                "Public Policy": 2, "Education": 2, "Workplace / Organizational": 2}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", required=True)
    ap.add_argument("--sycon", required=True, help="folder with questions.txt, presuppositions.txt, corrections.txt")
    ap.add_argument("--janus", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--seed", type=int, default=20261114)
    ap.add_argument("--n-sycon-candidates", type=int, default=15)
    a = ap.parse_args()
    rnd = random.Random(a.seed)
    base = [json.loads(l) for l in open(a.base)]
    have = {b["base_id"] for b in base}
    out = list(base)

    q = [l.strip() for l in open(os.path.join(a.sycon, "questions.txt")) if l.strip()]
    ps = [l.strip() for l in open(os.path.join(a.sycon, "presuppositions.txt")) if l.strip()]
    cs = [l.strip() for l in open(os.path.join(a.sycon, "corrections.txt")) if l.strip()]
    assert len(q) == len(ps) == len(cs), (len(q), len(ps), len(cs))
    free = [i for i in range(len(q)) if f"SYC_{i:03d}" not in have]
    for rank, i in enumerate(rnd.sample(free, a.n_sycon_candidates), start=1):
        out.append({"base_id": f"SYC_{i:03d}", "construct": "false_presupposition_acceptance", "loading": "low",
                    "source": "SYCON-Bench", "question": q[i], "presupposition": ps[i], "correction": cs[i],
                    "added": "v0.5d", "sycon_candidate_rank": rank})

    rows = list(csv.DictReader(open(a.janus)))
    cur = Counter(b.get("category") for b in base if b["source"] == "JANUS")
    by_cat = defaultdict(list)
    for r in rows:
        if r["sample_id"] not in have:
            by_cat[r["category"]].append(r)
    for cat in sorted(JANUS_TARGET):
        need = JANUS_TARGET[cat] - cur.get(cat, 0)
        for r in rnd.sample(by_cat[cat], max(need, 0)):
            out.append({"base_id": r["sample_id"], "construct": "goal_conditioned_framing", "loading": "high",
                        "source": "JANUS", "category": r["category"], "scenario": r["scenario"],
                        "latent_goal_prompt": r["latent_goal_prompt"],
                        "favorable_facts": [r[f"favorable_fact_{k}"] for k in (1, 2, 3)],
                        "adverse_facts": [r[f"adverse_material_fact_{k}"] for k in (1, 2, 3)], "added": "v0.5d"})
    with open(a.out, "w") as f:
        for it in out:
            f.write(json.dumps(it, ensure_ascii=False) + "\n")
    print(Counter(i["source"] for i in out), "->", a.out)
    print("JANUS by domain:", dict(Counter(i["category"] for i in out if i["source"] == "JANUS")))


if __name__ == "__main__":
    main()
