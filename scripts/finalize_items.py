"""Finalize the 60 questions after the ingredient run.

  python3 -I scripts/finalize_items.py --candidates studyb/items_candidates.jsonl \
      --ingredients studyb/full/ingredients.jsonl --out studyb/items_60.jsonl [--exclude SYC_116,...]

Keeps every item that is not a SYCON candidate. Among the new SYCON candidates (sycon_candidate_rank), keeps the
first 10 in rank order whose ingredients parsed and have a non-null kernel_clause,
skipping any id passed with --exclude (e.g. after reviewing the ingredients). Prints what was dropped and why.
Run assemble_versions.py etc. with --items studyb/items_60.jsonl afterwards.
"""
import argparse, json


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--candidates", required=True)
    ap.add_argument("--ingredients", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--n-sycon-new", type=int, default=None,
                    help="default: as many as needed to reach --sycon-target after exclusions")
    ap.add_argument("--sycon-target", type=int, default=20)
    ap.add_argument("--exclude", default="", help="comma-separated base_ids to drop (e.g. after review)")
    ap.add_argument("--exclude-file", default=None, help="studyb/exclusions.tsv: base_id<TAB>date<TAB>reason per line")
    a = ap.parse_args()
    cands = [json.loads(l) for l in open(a.candidates)]
    ings = {json.loads(l)["base_id"]: json.loads(l) for l in open(a.ingredients)}
    excl = {x.strip() for x in a.exclude.split(",") if x.strip()}
    reasons = {}
    if a.exclude_file:
        for line in open(a.exclude_file):
            if line.strip() and not line.startswith("#"):
                parts = line.rstrip("\n").split("\t")
                excl.add(parts[0].strip()); reasons[parts[0].strip()] = parts[-1].strip()
    keep, report, n_new = [], [], 0
    if a.n_sycon_new is None:
        base_sycon = sum(1 for it in cands if it["source"] == "SYCON-Bench" and "sycon_candidate_rank" not in it
                         and it["base_id"] not in excl)
        a.n_sycon_new = max(0, a.sycon_target - base_sycon)
    for it in cands:
        bid = it["base_id"]
        if bid in excl:
            report.append(f"- dropped {bid}: excluded by hand" + (f" ({reasons[bid]})" if bid in reasons else "")); continue
        if "sycon_candidate_rank" not in it:
            keep.append(it); continue
        r = ings.get(bid)
        if n_new >= a.n_sycon_new:
            report.append(f"- dropped {bid} (rank {it['sycon_candidate_rank']}): not needed, {a.n_sycon_new} already kept"); continue
        if not r or r.get("parse_error") or not r.get("ingredients"):
            report.append(f"- dropped {bid} (rank {it['sycon_candidate_rank']}): no usable ingredients"); continue
        if not (r["ingredients"].get("kernel_clause") or "").strip():
            report.append(f"- dropped {bid} (rank {it['sycon_candidate_rank']}): no genuine kernel of truth"); continue
        keep.append(it); n_new += 1
    from collections import Counter
    cnt = Counter(i["source"] for i in keep)
    with open(a.out, "w") as f:
        for it in keep:
            f.write(json.dumps(it, ensure_ascii=False) + "\n")
    print("\n".join(report) or "nothing dropped")
    print(dict(cnt), "->", a.out)
    if n_new < a.n_sycon_new:
        print(f"WARNING: only {n_new} new SYCON items passed screening; add candidates with extend_items.py "
              f"(--n-sycon-candidates) or accept fewer.")


if __name__ == "__main__":
    main()
