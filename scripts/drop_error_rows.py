"""Remove ingredient rows that have ERRORs in the check report, so the next run_ingredients.py call regenerates them.

  python3 -I scripts/drop_error_rows.py --ingredients studyb/full/ingredients.jsonl --report studyb/full/ingredients_check.md

The removed rows are appended to <ingredients>.dropped.jsonl (nothing is lost). Prints the ids it removed.
Regeneration is a fresh model write; no judge has seen these questions, so redoing them does not bias anything.
"""
import argparse, json, re


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ingredients", required=True)
    ap.add_argument("--report", required=True)
    a = ap.parse_args()
    bad, cur = set(), None
    for line in open(a.report):
        m = re.match(r"## (\S+) \(", line)
        if m:
            cur = m.group(1)
        elif cur and "**ERROR**" in line:
            bad.add(cur)
    rows = [l for l in open(a.ingredients) if l.strip()]
    keep = [l for l in rows if json.loads(l)["base_id"] not in bad]
    if bad:
        with open(a.ingredients + ".dropped.jsonl", "a") as f:
            f.writelines(l for l in rows if json.loads(l)["base_id"] in bad)
        with open(a.ingredients, "w") as f:
            f.writelines(keep)
    print(" ".join(sorted(bad)) if bad else "")


if __name__ == "__main__":
    main()
