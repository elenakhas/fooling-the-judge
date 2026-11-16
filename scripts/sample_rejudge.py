"""Seeded, stratified sample of versions for the noise re-judge.

  python3 -I scripts/sample_rejudge.py --versions studyb/full/versions.jsonl --out studyb/full/rejudge_versions.jsonl \
      [--frac 0.10] [--all-partial]

Stratified by dataset x stance (10% of each, at least 1). --all-partial adds every partial version (option: judge all
partials twice). Judge the sample into a separate folder (the judge cache is per folder), then compare with
judge_consistency.py.
"""
import argparse, json, math, random
from collections import defaultdict


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--versions", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--frac", type=float, default=0.10)
    ap.add_argument("--seed", type=int, default=20261115)
    ap.add_argument("--all-partial", action="store_true")
    a = ap.parse_args()
    vs = [json.loads(l) for l in open(a.versions)]
    strata = defaultdict(list)
    for v in vs:
        strata[(v["dataset"] if "dataset" in v else v.get("source"), v["stance"])].append(v)
    rnd = random.Random(a.seed)
    keep = {}
    for k in sorted(strata, key=str):
        group = sorted(strata[k], key=lambda v: v["version_id"])
        if a.all_partial and k[1] == "partial":
            pick = group
        else:
            pick = rnd.sample(group, max(1, math.ceil(a.frac * len(group))))
        for v in pick:
            keep[v["version_id"]] = v
    with open(a.out, "w") as f:
        for v in vs:
            if v["version_id"] in keep:
                f.write(json.dumps(v) + "\n")
    print(f"{len(keep)} of {len(vs)} versions -> {a.out}")


if __name__ == "__main__":
    main()
