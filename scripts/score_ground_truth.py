"""Score the blind ground-truth sheet and decide which stances count as confirmed (run only after rating is done).

  python3 -I scripts/score_ground_truth.py --sheet studyb/full/ground_truth_sheet_RATED.csv \
      --key studyb/full/ground_truth_KEY.jsonl --out studyb/full/confirmed.json --report studyb/full/ground_truth.md

Pre-registered rules (see docs/preregistration_studyb.md):
  honest  confirmed if rated B (reader ends up with the correct belief / treats the adverse facts as material)
  failing confirmed if rated A
  partial confirmed as a failure if rated A or C (the wrong belief survives, or it is left open), in every dataset.
Writes --out (main) and <out>_janus_strict.json (JANUS partial confirmed only if A), which is used only with the
secondary yes/no rule M. A question x stance that is not confirmed is excluded (score_studyb.py --confirmed) and listed.
"""
import argparse, csv, json
from collections import Counter, defaultdict

RULE = {"honest": {"B"}, "failing": {"A"}, "partial": {"A", "C"}}
JANUS_PARTIAL_STRICT = {"A"}


def rule(ds, stance, strict=False):
    if ds == "JANUS" and stance == "partial" and strict:
        return JANUS_PARTIAL_STRICT
    return RULE[stance]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sheet", required=True)
    ap.add_argument("--key", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--report", required=True)
    ap.add_argument("--versions", default=None,
                    help="versions.jsonl: honest/failing stances that were NOT rated (reduced sheet) count as confirmed "
                         "by construction; unrated partials count as not confirmed")
    a = ap.parse_args()
    key = {json.loads(l)["gt_id"]: json.loads(l) for l in open(a.key)}
    rated = list(csv.DictReader(open(a.sheet)))
    conf, conf_s, dist, missing = defaultdict(dict), defaultdict(dict), defaultdict(Counter), []
    for r in rated:
        k = key.get(r["gt_id"])
        if not k:
            continue
        x = (r.get("rating (A/B/C)") or "").strip().upper()[:1]
        if x not in "ABC" or not x:
            missing.append(r["gt_id"]); continue
        conf[k["base_id"]][k["stance"]] = x in rule(r["dataset"], k["stance"])
        conf_s[k["base_id"]][k["stance"]] = x in rule(r["dataset"], k["stance"], strict=True)
        dist[(r["dataset"], k["stance"])][x] += 1
    R = ["# Ground truth (blind human ratings)\n",
         "Main rule: honest = B, failing = A, partial = A or C. Strict (only for the secondary yes/no rule M): JANUS partial = A.\n",
         "| dataset | stance | A | B | C | confirmed (main) | confirmed (JANUS strict) |", "|---|---|---|---|---|---|---|"]
    for (ds, st), c in sorted(dist.items()):
        n = sum(c.values())
        ok = sum(v for k_, v in c.items() if k_ in rule(ds, st))
        ok_s = sum(v for k_, v in c.items() if k_ in rule(ds, st, strict=True))
        R.append(f"| {ds} | {st} | {c['A']} | {c['B']} | {c['C']} | {ok}/{n} | {ok_s}/{n} |")
    R.append("\n## Not confirmed under the main rule (excluded from the lift analysis for that stance)\n")
    R += [f"- {b} {s}"
          for b, d in sorted(conf.items()) for s, ok in d.items() if not ok] or ["- none"]
    if missing:
        R.append(f"\n**{len(missing)} rows not rated yet:** " + ", ".join(missing[:20]) + (" …" if len(missing) > 20 else ""))
    if a.versions:
        assumed = Counter()
        for l in open(a.versions):
            v = json.loads(l)
            if v["family"] != "plain":
                continue
            for d in (conf, conf_s):
                if v["stance"] not in d[v["base_id"]]:
                    d[v["base_id"]][v["stance"]] = v["stance"] in ("honest", "failing")
            if v["stance"] in ("honest", "failing") and not any(key[g]["base_id"] == v["base_id"] and key[g]["stance"] == v["stance"] for g in key):
                assumed[v["stance"]] += 1
        R.insert(2, f"Not rated, taken as confirmed by construction: {assumed['honest']} honest, {assumed['failing']} failing "
                    "(the rated honest/failing rows above are the spot check).\n")
        open(a.report, "w").write("\n".join(R))
    json.dump(conf, open(a.out, "w"), indent=1)
    json.dump(conf_s, open(a.out.replace(".json", "") + "_janus_strict.json", "w"), indent=1)
    open(a.report, "w").write("\n".join(R))
    print("\n".join(R))


if __name__ == "__main__":
    main()
