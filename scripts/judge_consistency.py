"""Judge consistency (noise baseline, analysis step 6b): compare two runs of the same judges on the same versions.

  python3 -I scripts/judge_consistency.py results/judgments/studyb_pilot3 results/judgments/studyb_pilot3_rep \
      --report studyb/pilot3/consistency.md

For every judge file present in both folders (matched by file name, e.g. arm0__claude-sonnet-5-5.jsonl):
  - flip rate of the binary verdict (SYC vs PASS) and of the fine label (e.g. DIR-SYC vs CS-SYC, A vs C, [0,1,1] vs [1,1,1]);
  - flips broken down by dataset, stance and condition;
  - the list of flipped versions, so you can see whether "misses" in the first run were stable.
A lift smaller than the flip rate of its cell cannot be told apart from run-to-run noise.
"""
import argparse, glob, json, os
from collections import defaultdict


def load(path):
    out = {}
    for l in open(path):
        if l.strip():
            r = json.loads(l)
            out[r["version_id"]] = r
    return out


def rate(pairs):
    return f"{sum(pairs)}/{len(pairs)} ({sum(pairs)/len(pairs):.0%})" if pairs else "—"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run_a")
    ap.add_argument("run_b")
    ap.add_argument("--report", required=True)
    a = ap.parse_args()
    R = ["# Judge consistency\n", f"Run A: `{a.run_a}` · Run B: `{a.run_b}`\n"]
    files = sorted(set(os.path.basename(p) for p in glob.glob(os.path.join(a.run_a, "arm*.jsonl"))) &
                   set(os.path.basename(p) for p in glob.glob(os.path.join(a.run_b, "arm*.jsonl"))))
    if not files:
        R.append("No judge files present in both folders.")
    summary = ["| judge file | versions in both | binary flips | label flips |", "|---|---|---|---|"]
    detail = []
    for fn in files:
        A, B = load(os.path.join(a.run_a, fn)), load(os.path.join(a.run_b, fn))
        common = sorted(set(A) & set(B))
        bin_flip, lab_flip, by = [], [], defaultdict(list)
        flipped = []
        for v in common:
            x, y = A[v], B[v]
            if not x.get("parsed_binary") or not y.get("parsed_binary"):
                continue
            fb = x["parsed_binary"] != y["parsed_binary"]
            fl = str(x.get("parsed_label")) != str(y.get("parsed_label"))
            bin_flip.append(fb); lab_flip.append(fl)
            for key in (("dataset", x["dataset"]), ("stance", x["stance"]), ("condition", x["family"])):
                by[key].append(fb)
            if fb or fl:
                flipped.append((v, x.get("parsed_label"), y.get("parsed_label"), fb))
        summary.append(f"| {fn.replace('.jsonl', '')} | {len(common)} | {rate(bin_flip)} | {rate(lab_flip)} |")
        detail.append(f"\n## {fn.replace('.jsonl', '')}\n")
        for kind in ("dataset", "stance", "condition"):
            cells = [f"{k[1]} {rate(v)}" for k, v in sorted(by.items()) if k[0] == kind]
            detail.append(f"- binary flips by {kind}: " + "; ".join(cells))
        if flipped:
            detail.append("\n| version | run A | run B | verdict flipped? |\n|---|---|---|---|")
            detail += [f"| {v} | {la} | {lb} | {'**yes**' if fb else 'label only'} |" for v, la, lb, fb in flipped]
        else:
            detail.append("\nNo flips.")
    R += summary + detail
    os.makedirs(os.path.dirname(os.path.abspath(a.report)), exist_ok=True)
    open(a.report, "w").write("\n".join(R))
    print("\n".join(summary))
    print(f"-> {a.report}")


if __name__ == "__main__":
    main()
