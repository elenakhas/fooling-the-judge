"""Assemble versions from ingredients + frames, then check them.

  python3 -I scripts/assemble_versions.py --items studyb/items_60.jsonl --ingredients studyb/full/ingredients.jsonl \
      --frames studyb/frames_pilot.json --out studyb/full/versions.jsonl --report studyb/full/versions_check.md

Design:
  stances    honest · failing (carries the wrong belief as fact) · partial (correct fact stated, belief left standing)
  conditions plain · warmth · concession · scope · hedge · booster · credibility · persuasion · stacked
Frames are stance-neutral: the same marker words go into all three stances of a question. Question i of a dataset
(sorted by base_id) gets phrasing i of each marker pool; the stacked version reuses those same phrasings.
A condition whose required ingredient is null is skipped for that question in every stance; a stance whose core is
null (e.g. no partial_core) is skipped in every condition.

Each output row is ready for judge_studyb.py: version_id (base::stance::condition::vI), base_id, dataset, stance,
family (= condition), frame_variant, t2, plus the context fields each dataset's judges need. ("clarity" is always
"quiet"; the field is kept for compatibility with the scoring scripts.)
"""
import argparse, json, os, re, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from prompts_ingredients import banned_hits

FAMILIES = ["plain", "warmth", "concession", "scope", "hedge", "booster", "credibility", "persuasion", "stacked"]
STANCES = {"EduFrameTrap": {"honest": "honest_core", "failing": "failing_core", "partial": "partial_core"},
           "SYCON-Bench": {"honest": "honest_core", "failing": "failing_core", "partial": "partial_core"},
           "JANUS": {"honest": "adverse_honest", "failing": "adverse_downplayed", "partial": "adverse_partial"}}


def lc_first(s, protect_text=""):
    """Lower-case the first letter unless the first word looks like a proper noun, formula or acronym.
    Proper noun = the same capitalised word appears mid-sentence somewhere in the item's source/ingredient text."""
    s = (s or "").strip()
    w = re.match(r"[A-Za-z][\w'’-]*", s)
    if not w:
        return s
    word = w.group()
    if word == "I" or any(c.isupper() or c.isdigit() for c in word[1:]):
        return s
    for m in re.finditer(r"\b" + re.escape(word) + r"\b", protect_text):
        before = protect_text[:m.start()].rstrip(" \t")
        if before and before[-1] not in ".!?:\"\n(*-•":
            return s
    return s[0].lower() + s[1:]


def uc_first(s):
    s = (s or "").strip()
    w = re.match(r"[A-Za-z][\w'’-]*", s)
    if not s or not w or any(c.isupper() or c.isdigit() for c in w.group()[1:]):
        return s
    return s[0].upper() + s[1:]


def tidy(text):
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"\s+([,.;:])", r"\1", text)
    text = re.sub(r"\.\.+", ".", text)
    return text


def resolve(frames, key, ds):
    """Look up frames[key][ds], following 'same as X' references; 'all' applies to every dataset."""
    node = frames[key]
    v = node.get(ds, node.get("all"))
    if isinstance(v, str) and v.startswith("same as "):
        v = node[v[len("same as "):]]
    return v


def context(item):
    src = item["source"]
    if src == "EduFrameTrap":
        keep = ("misconception", "standard_truth", "obscure_context", "pressure_mode", "s1", "t1", "s2")
        c = {k: item.get(k, "") for k in keep}
        c["mode"] = item.get("pressure_mode", "")
        return c
    if src == "SYCON-Bench":
        return {k: item[k] for k in ("question", "presupposition", "correction")}
    if src == "JANUS":
        return {"scenario": item["scenario"], "latent_goal_prompt": item["latent_goal_prompt"],
                "adverse_facts": item["adverse_facts"], "favorable_facts": item["favorable_facts"],
                "adverse_list": "\n".join(f"- N{i+1}: {f}" for i, f in enumerate(item["adverse_facts"]))}
    raise ValueError(src)


def markers(frames, ds, i, reframe):
    """Phrasing i of every marker pool for this dataset (scope phrasings needing {reframe} are skipped if it is null)."""
    out = {}
    for fam in ("warmth", "concession", "scope", "hedge", "booster", "credibility", "persuasion"):
        pool = resolve(frames["pools"], fam, ds)
        if not reframe:
            pool = [p for p in pool if "{reframe}" not in p]
        out[fam] = pool[i % len(pool)].replace("{reframe}", reframe or "")
    return out


def question_order(items):
    """Index of each question within its dataset (sorted by base_id): question i gets phrasing i of every pool."""
    order = {}
    for bid in sorted(items):
        ds = items[bid]["source"]
        order[bid] = sum(1 for b in order if items[b]["source"] == ds)
    return order


def load_fitted(path):
    """base_id -> {family: phrasing to use} from fit_markers.py output (failed fits already fall back to the original)."""
    out = {}
    for l in open(path):
        r = json.loads(l)
        out[r["base_id"]] = {f: m["used"] for f, m in r["markers"].items()}
    return out


def slots(item, ing, stance, M, protect):
    g = lambda k: (ing.get(k) or "").strip()
    ds = item["source"]
    core = g(STANCES[ds][stance])
    d = {f"m_{k}": v for k, v in M.items()}
    d["m_credibility_lc"] = lc_first(M["credibility"])
    if ds == "JANUS":
        d.update(fav=g("favorable_core"), adv=core, adv_lc=lc_first(core, protect))
    else:
        kernel = g("kernel_clause").rstrip(".")
        edge_s = (f"In {g('edge_setting')}, {lc_first(g('edge_claim'), protect)}"
                  if g("edge_setting") and g("edge_claim") else "")
        d.update(core=core, core_lc=lc_first(core, protect), bg=g("neutral_background"),
                 kernel=kernel, kernel_s=(uc_first(kernel) + ".") if kernel else "",
                 conc=f"{M['concession']} {kernel}." if kernel else "",
                 edge_s=edge_s,
                 scope_edge=M["scope"] if edge_s else "", scope_bg="" if edge_s else M["scope"])
    return d


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--items", required=True)
    ap.add_argument("--ingredients", required=True)
    ap.add_argument("--frames", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--report", required=True)
    ap.add_argument("--fitted", default=None, help="markers_fitted.jsonl from fit_markers.py (optional)")
    a = ap.parse_args()
    items = {json.loads(l)["base_id"]: json.loads(l) for l in open(a.items)}
    ings = {json.loads(l)["base_id"]: json.loads(l) for l in open(a.ingredients)}
    frames = json.load(open(a.frames))
    order = question_order(items)
    fitted = load_fitted(a.fitted) if a.fitted else {}

    out, R, n_err = [], ["# Version checks\n"], 0
    for bid, item in sorted(items.items()):
        r = ings.get(bid)
        if not r or not r.get("ingredients") or r.get("parse_error"):
            R.append(f"- **SKIP** {bid}: no usable ingredients"); continue
        ing, ds, i = r["ingredients"], item["source"], order[bid]
        src_keys = ("misconception", "standard_truth", "obscure_context", "question", "presupposition", "correction",
                    "scenario", "latent_goal_prompt")
        src_vals = [item.get(k) for k in src_keys] + item.get("adverse_facts", []) + item.get("favorable_facts", [])
        protect = "\n".join(str(v) for v in src_vals + list(ing.values()) if isinstance(v, str))
        M = markers(frames, ds, i, (ing.get("reframe_setting") or "").strip())
        M_orig = dict(M)
        M.update({f: v for f, v in fitted.get(bid, {}).items() if f in M})
        templates = resolve(frames, "templates", ds)
        stances = [s for s, f in STANCES[ds].items() if ing.get(f)]
        for s, f in STANCES[ds].items():
            if s not in stances:
                R.append(f"- n/a {bid} stance {s}: {f} is null")
        for fam in FAMILIES:
            req = (frames.get("requires", {}).get(fam) or {}).get(ds, [])
            if any(not ing.get(x) for x in req):
                R.append(f"- n/a {bid} {fam}: missing {req}"); continue
            tmpl = templates[fam]
            for stance in stances:
                S = slots(item, ing, stance, M, protect)
                S["m"] = M.get(fam, "")
                try:
                    text = tidy(tmpl.format(**S))
                except KeyError as e:
                    R.append(f"- **ERROR** {bid} {fam} {stance}: unknown slot {e}"); n_err += 1; continue
                vid = f"{bid}::{stance}::{fam}::v{i}"
                row = {"version_id": vid, "example_id": vid, "base_id": bid, "dataset": ds, "clarity": "quiet",
                       "stance": stance, "family": fam, "frame_variant": i, "t2": text, "response": text,
                       "n_words": len(text.split()), "ingredient_model": r.get("model"),
                       "markers": {k: v for k, v in M.items() if fam == k or fam == "stacked"},
                       "markers_original": {k: v for k, v in M_orig.items() if (fam == k or fam == "stacked") and v != M[k]}}
                row.update(context(item))
                problems = []
                for slot in re.findall(r"\{([a-z_]+)\}", tmpl):
                    v = (S[slot] or "").rstrip(".")
                    if v and v.lower() not in text.lower():
                        problems.append(f"slot '{slot}' not found verbatim")
                if fam == "plain":
                    src = json.dumps(item).lower()     # words quoted from the dataset's own facts are content, not frames
                    hits = [h for h in banned_hits(text) if not re.search(r"\b" + re.escape(h.lower()) + r"\b", src)]
                    if hits:
                        problems.append(f"plain version contains frame vocabulary {hits}")
                if problems:
                    n_err += len(problems)
                    R.append(f"- **ERROR** {vid}: " + "; ".join(problems))
                out.append(row)
    R.append("\n## Length (words) per question\n")
    R.append("| base_id | stance | " + " | ".join(FAMILIES) + " |")
    R.append("|---|---|" + "---|" * len(FAMILIES))
    for bid in sorted(items):
        for st in ("honest", "failing", "partial"):
            L = {r["family"]: r["n_words"] for r in out if r["base_id"] == bid and r["stance"] == st}
            if L:
                R.append(f"| {bid} | {st} | " + " | ".join(str(L.get(f, "n/a")) for f in FAMILIES) + " |")
    R.insert(1, f"**{len(out)} versions from {len(items)} questions · {n_err} errors**\n")
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    with open(a.out, "w") as f:
        for r in out:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    open(a.report, "w").write("\n".join(R))
    print(f"{len(out)} versions, {n_err} errors -> {a.out}; report -> {a.report}")
    sys.exit(1 if n_err else 0)


if __name__ == "__main__":
    main()
