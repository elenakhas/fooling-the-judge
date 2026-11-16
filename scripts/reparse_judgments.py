"""Re-parse stored judge answers with the current parser (no API calls). Keeps a .bak copy of each file.

  python3 -I scripts/reparse_judgments.py results/judgments/studyb_full/*.jsonl
"""
import json, os, shutil, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from judge_studyb import PROMPTS, parse

for fn in sys.argv[1:]:
    rows = [json.loads(l) for l in open(fn) if l.strip()]
    before = sum(1 for r in rows if r.get("parsed_binary"))
    for r in rows:
        kind = PROMPTS[(r["arm"], r["dataset"])][2]
        r["parsed_label"], r["parsed_binary"] = parse(kind, r.get("raw"))
    after = sum(1 for r in rows if r.get("parsed_binary"))
    if after != before:
        shutil.copy(fn, fn + ".bak")
        with open(fn, "w") as f:
            f.writelines(json.dumps(r) + "\n" for r in rows)
    print(f"{fn}: parsed {before} -> {after} of {len(rows)}")
