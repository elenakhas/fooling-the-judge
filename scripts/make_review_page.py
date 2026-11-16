"""Build a review page (one self-contained HTML file) and a review sheet (CSV) for reading versions by hand.

  python3 -I scripts/make_review_page.py --items studyb/items_60.jsonl --ingredients studyb/full/ingredients.jsonl \
      --versions studyb/full/versions.jsonl --judgments results/judgments/studyb_full \
      --html studyb/full/review.html --csv studyb/full/review.csv

The page groups versions by question, with the stances (honest, failing, partial) side by side for each condition. Frame words
(everything that is not an ingredient) are highlighted yellow, verdict sentences blue. Judge verdicts are shown as
badges; hover a badge for the judge's rationale. Each version has "reads naturally?" and "stance clear?" ratings and
a comment box; ratings are kept in the browser and can be exported as CSV. --judgments is optional; --frames adds
a section listing every phrasing in every marker pool, for reviewing the pools themselves.
"""
import argparse, csv, glob, html, json, os, re

FAMS = ("plain", "warmth", "concession", "scope", "hedge", "booster", "credibility", "persuasion", "stacked")
FIT = {}
ARM_NAMES = {"arm0": "published", "arm1": "no reference", "arm2": "reader belief", "arm3": "checklist"}


def load_judgments(d):
    out = {}   # version_id -> {arm: (short, flag, rationale)}
    for fn in sorted(glob.glob(os.path.join(d, "arm*__*.jsonl"))) if d else []:
        for l in open(fn):
            if not l.strip():
                continue
            r = json.loads(l)
            raw = r.get("raw") or ""
            try:
                o = json.loads(raw[raw.index("{"):raw.rindex("}") + 1])
            except (ValueError, json.JSONDecodeError):
                o = {}
            rat = o.get("rationale") or ""
            if isinstance(o.get("scores"), list):
                rat = " · ".join(f"{s.get('fact_id')}: {s.get('score')} {s.get('rationale', '')}" for s in o["scores"]
                                 if isinstance(s, dict))
            if not rat and o:
                rat = "; ".join(f"{k}={v}" for k, v in o.items() if k.startswith("Q") and not k.endswith("quote"))
            lab = r.get("parsed_label")
            short = {"1": "PASS", "0": "SYC"}.get(lab, lab) if r["dataset"] == "SYCON-Bench" and r["arm"] == "arm0" else lab
            out.setdefault(r["version_id"], {})[r["arm"]] = (str(short), r.get("parsed_binary"), rat or raw[:400])
    return out


def mask_text(text, ing, verdicts):
    """0 = frame word, 1 = ingredient content, 2 = verdict sentence (char-level)."""
    low = text.lower()
    m = [0] * len(text)
    pieces = [v for v in ing.values() if isinstance(v, str) and v.strip()]
    if ing.get("edge_setting"):
        pieces.append(f"In {ing['edge_setting']},")
    if ing.get("reframe_setting"):
        pieces.append(f"In {ing['reframe_setting']},")
    for p in sorted(pieces, key=len, reverse=True):
        p2 = p.strip().rstrip(".").lower()
        for mt in re.finditer(re.escape(p2), low):
            for i in range(mt.start(), min(mt.end() + 1, len(text))):   # include the trailing period
                if m[i] == 0:
                    m[i] = 1
    for v in verdicts:
        v2 = v.strip().rstrip(".").lower()
        for mt in re.finditer(re.escape(v2), low):
            for i in range(mt.start(), min(mt.end() + 1, len(text))):
                m[i] = 2
    # whitespace and punctuation between two content runs count as content
    for i, ch in enumerate(text):
        if m[i] == 0 and not ch.isalnum():
            left = next((m[j] for j in range(i - 1, -1, -1) if text[j].isalnum() or m[j]), 1)
            right = next((m[j] for j in range(i + 1, len(text)) if text[j].isalnum() or m[j]), 1)
            if left and right:
                m[i] = min(left, right)
    return m


def render(text, m):
    out, cur, buf = [], None, []
    cls = {0: "fr", 1: None, 2: "vd"}

    def flush():
        if buf:
            s = html.escape("".join(buf))
            out.append(f'<span class="{cls[cur]}">{s}</span>' if cls[cur] else s)

    for ch, k in zip(text, m):
        if k != cur:
            flush(); buf.clear(); cur = k
        buf.append(ch)
    flush()
    return "".join(out)


def context_html(item):
    e = html.escape
    if item["source"] == "EduFrameTrap":
        return (f"<p><b>Misconception:</b> {e(item.get('misconception', ''))}</p>"
                f"<p><b>Correct (usual setting):</b> {e(item.get('standard_truth', ''))}</p>"
                f"<details><summary>Conversation so far</summary><p><b>Student:</b> {e(item.get('s1', ''))}</p>"
                f"<p><b>Tutor:</b> {e(item.get('t1', ''))}</p><p><b>Student:</b> {e(item.get('s2', ''))}</p></details>")
    if item["source"] == "SYCON-Bench":
        return (f"<p><b>Question:</b> {e(item['question'])}</p><p><b>False premise:</b> {e(item['presupposition'])}</p>"
                f"<p><b>Correction:</b> {e(item['correction'])}</p>")
    return (f"<p><b>Scenario:</b> {e(item['scenario'])}</p><p><b>Writer's incentive:</b> {e(item['latent_goal_prompt'])}</p>"
            f"<p><b>Adverse facts:</b> {' / '.join(e(f) for f in item['adverse_facts'])}</p>")


CSS = """
:root{--bg:#fff;--fg:#1d1d1f;--mut:#6b6b70;--line:#e3e3e6;--fr:#fff1a8;--vd:#d6e6ff;--ok:#1f7a3a;--bad:#b3261e;--card:#fafafa}
@media (prefers-color-scheme:dark){:root{--bg:#1b1b1d;--fg:#ececee;--mut:#a0a0a6;--line:#38383c;--fr:#5c5216;--vd:#1e3a63;--ok:#5fd18a;--bad:#ff8a80;--card:#232326}}
*{box-sizing:border-box}body{margin:0;font:15px/1.5 -apple-system,system-ui,Segoe UI,sans-serif;background:var(--bg);color:var(--fg)}
header{position:sticky;top:0;background:var(--bg);border-bottom:1px solid var(--line);padding:10px 20px;z-index:2;display:flex;gap:14px;flex-wrap:wrap;align-items:center}
header h1{font-size:16px;margin:0 12px 0 0}select,button,input{font:inherit}button{cursor:pointer;border:1px solid var(--line);background:var(--card);color:var(--fg);border-radius:6px;padding:4px 10px}
main{padding:10px 20px 60px;max-width:1900px}section.q{border-top:2px solid var(--line);margin-top:22px;padding-top:6px}
section.q h2{font-size:17px;margin:6px 0}.ctx{color:var(--mut);font-size:14px}.ctx p{margin:3px 0}
h3{font-size:14px;text-transform:uppercase;letter-spacing:.05em;color:var(--mut);margin:16px 0 6px}
table{width:100%;border-collapse:collapse;table-layout:fixed}td,th{border:1px solid var(--line);vertical-align:top;padding:8px 10px}
th{background:var(--card);font-weight:600;text-align:left;font-size:13px}td.fam{width:110px;font-size:13px;font-weight:600;background:var(--card)}
.txt{white-space:pre-wrap}.fr{background:var(--fr);border-radius:3px}.vd{background:var(--vd);border-radius:3px}
.meta{margin-top:6px;font-size:12px;color:var(--mut);display:flex;flex-wrap:wrap;gap:6px;align-items:center}
.b{border-radius:10px;padding:1px 7px;border:1px solid currentColor;cursor:help}.b.p{color:var(--ok)}.b.s{color:var(--bad)}
.rate{margin-top:6px;display:flex;gap:6px;flex-wrap:wrap;font-size:12px}.rate input[type=text]{flex:1;min-width:140px}
.legend span{padding:0 4px}.hide-j .meta .b{display:none}.hide-h .fr,.hide-h .vd{background:none}
"""

JS = """
const KEY='ftj-review:'+document.title;let R={};try{R=JSON.parse(localStorage.getItem(KEY)||'{}')}catch(e){}
function save(){try{localStorage.setItem(KEY,JSON.stringify(R))}catch(e){}}
document.querySelectorAll('[data-v]').forEach(el=>{const v=el.dataset.v,f=el.dataset.f;if(R[v]&&R[v][f]!=null)el.value=R[v][f];
 el.addEventListener('change',()=>{R[v]=R[v]||{};R[v][f]=el.value;save()});el.addEventListener('input',()=>{R[v]=R[v]||{};R[v][f]=el.value;save()})});
function apply(){const ds=document.getElementById('fds').value,cl=document.getElementById('fcl').value;
 document.querySelectorAll('section.q').forEach(s=>s.style.display=(ds==='all'||s.dataset.ds===ds)?'':'none');
 document.querySelectorAll('.cl').forEach(s=>s.style.display=(cl==='all'||s.dataset.cl===cl)?'':'none')}
document.getElementById('fds').onchange=apply;document.getElementById('fcl').onchange=apply;
document.getElementById('tj').onchange=e=>document.body.classList.toggle('hide-j',!e.target.checked);
document.getElementById('th').onchange=e=>document.body.classList.toggle('hide-h',!e.target.checked);
document.getElementById('exp').onclick=()=>{const rows=[['version_id','natural','stance_clear','comment']];
 document.querySelectorAll('td[data-vid]').forEach(td=>{const v=td.dataset.vid,r=R[v]||{};rows.push([v,r.natural||'',r.stance||'',r.comment||''])});
 const q=s=>'"'+String(s).replace(/"/g,'""')+'"';const blob=new Blob([rows.map(r=>r.map(q).join(',')).join('\\n')],{type:'text/csv'});
 const a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download='review_ratings.csv';a.click()};
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--items", required=True)
    ap.add_argument("--ingredients", required=True)
    ap.add_argument("--versions", required=True)
    ap.add_argument("--judgments", default=None)
    ap.add_argument("--html", required=True)
    ap.add_argument("--csv", required=True)
    ap.add_argument("--title", default=None)
    ap.add_argument("--frames", default=None)
    ap.add_argument("--fitted", default=None, help="markers_fitted.jsonl: shows which phrasings were adapted per question")
    a = ap.parse_args()
    items = {json.loads(l)["base_id"]: json.loads(l) for l in open(a.items)}
    ings = {json.loads(l)["base_id"]: (json.loads(l).get("ingredients") or {}) for l in open(a.ingredients)}
    vers = [json.loads(l) for l in open(a.versions)]
    J = load_judgments(a.judgments)
    global FIT
    FIT = {json.loads(l)["base_id"]: json.loads(l)["markers"] for l in open(a.fitted)} if a.fitted else {}
    title = a.title or f"Review · {os.path.basename(os.path.dirname(os.path.abspath(a.versions)))}"
    by = {}
    for v in vers:
        by.setdefault(v["base_id"], {}).setdefault(v.get("clarity", "explicit"), {}).setdefault(v["family"], {})[v["stance"]] = v

    rows_csv, H = [], []
    datasets = sorted({v["dataset"] for v in vers})
    H.append(f"<!DOCTYPE html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>"
             f"<title>{html.escape(title)}</title><style>{CSS}</style></head><body><header><h1>{html.escape(title)}</h1>"
             "<label>Dataset <select id='fds'><option value='all'>all</option>" +
             "".join(f"<option>{html.escape(d)}</option>" for d in datasets) + "</select></label>"
             "<label style='display:none'>Clarity <select id='fcl'><option value='all'>all</option><option>quiet</option><option>explicit</option></select></label>"
             "<label><input type='checkbox' id='th' checked> highlights</label><label><input type='checkbox' id='tj' checked> judges</label>"
             "<button id='exp'>Export ratings (CSV)</button>"
             "<span class='legend'><span class='fr'>frame words</span> <span class='vd'>verdict sentence</span> · badges: "
             "<span class='b p'>PASS</span> <span class='b s'>flagged</span> (hover for rationale)</span></header><main>")
    if a.frames:
        fr = json.load(open(a.frames))
        H.append("<section class='q'><details><summary><b>Marker pools</b> (every phrasing; question i of a dataset gets "
                 "phrasing i)</summary>")
        for fam, by_ds in fr["pools"].items():
            H.append(f"<h3>{html.escape(fam)}</h3><p class='ctx'>{html.escape(fr.get('sources', {}).get(fam, ''))}</p>")
            for ds, pool in by_ds.items():
                if isinstance(pool, str):
                    H.append(f"<p class='ctx'>{html.escape(ds)}: {html.escape(pool)}</p>"); continue
                H.append(f"<p><b>{html.escape(ds)}</b></p><ol start='0'>" +
                         "".join(f"<li>{html.escape(x)}</li>" for x in pool) + "</ol>")
        H.append("</details></section>")
    for bid, by_cl in by.items():
        item, ing = items[bid], ings.get(bid, {})
        verdicts = [x for x in (ing.get("honest_verdict"), ing.get("failing_verdict")) if x]
        H.append(f"<section class='q' data-ds='{html.escape(item['source'])}'><h2>{html.escape(bid)} · {html.escape(item['source'])}</h2>"
                 f"<div class='ctx'>{context_html(item)}</div>")
        fm = FIT.get(bid)
        if fm:
            rows_f = [f"<li><b>{html.escape(f)}</b>: " + (f"<s>{html.escape(m['original'])}</s> → {html.escape(m['used'])}" if m['used'] != m['original']
                      else html.escape(m['used']) + (f" <span class='ctx'>(proposed '{html.escape(str(m['fitted']))}' rejected: {html.escape('; '.join(m['issues']))})</span>" if m['issues'] else ""))
                      + "</li>" for f, m in fm.items()]
            n_ad = sum(m['used'] != m['original'] for m in fm.values())
            H.append(f"<details><summary class='ctx'>Markers for this question ({n_ad} adapted to the topic)</summary><ul class='ctx'>{''.join(rows_f)}</ul></details>")
        for cl in ("quiet", "explicit"):
            if cl not in by_cl:
                continue
            sts = [x for x in ("honest", "failing", "partial") if any(x in d for d in by_cl[cl].values())]
            H.append(f"<div class='cl' data-cl='{cl}'>" + (f"<h3>{cl}</h3>" if cl != "quiet" else "") +
                     "<table><tr><th style='width:110px'>condition</th>" + "".join(f"<th>{x}</th>" for x in sts) + "</tr>")
            for fam in FAMS:
                pair = by_cl[cl].get(fam)
                if not pair:
                    H.append(f"<tr><td class='fam'>{fam}</td><td colspan='{len(sts)}' class='ctx'>not applicable for this question</td></tr>")
                    continue
                H.append(f"<tr><td class='fam'>{fam.replace('_', ' ')}</td>")
                for st in sts:
                    v = pair.get(st)
                    if not v:
                        H.append("<td></td>"); continue
                    vid = v["version_id"]
                    m = mask_text(v["t2"], ing, verdicts)
                    badges = []
                    for arm in ("arm0", "arm1", "arm2", "arm3"):
                        j = J.get(vid, {}).get(arm)
                        if j:
                            ok = j[1] == "PASS"
                            badges.append(f"<span class='b {'p' if ok else 's'}' title='{html.escape(j[2], quote=True)}'>"
                                          f"{ARM_NAMES[arm]}: {html.escape(j[0])}</span>")
                    H.append(f"<td data-vid='{html.escape(vid)}'><div class='txt'>{render(v['t2'], m)}</div>"
                             f"<div class='meta'>{v['n_words']} words · variant {v.get('frame_variant')} {''.join(badges)}</div>"
                             f"<div class='rate'><select data-v='{html.escape(vid)}' data-f='natural'><option value=''>reads naturally?</option>"
                             "<option>yes</option><option>awkward</option><option>no</option></select>"
                             f"<select data-v='{html.escape(vid)}' data-f='stance'><option value=''>stance clear?</option>"
                             "<option>yes</option><option>unclear</option><option>wrong</option></select>"
                             f"<input type='text' placeholder='comment' data-v='{html.escape(vid)}' data-f='comment'></div></td>")
                    jr = J.get(vid, {})
                    rows_csv.append({"version_id": vid, "dataset": v["dataset"], "base_id": bid, "clarity": cl, "stance": st,
                                     "family": fam, "n_words": v["n_words"], "text": v["t2"],
                                     **{f"{ARM_NAMES[k]}": (jr[k][0] if k in jr else "") for k in ARM_NAMES},
                                     "reads naturally? (yes/awkward/no)": "", "stance clear? (yes/unclear/wrong)": "", "comment": ""})
                H.append("</tr>")
            H.append("</table></div>")
        H.append("</section>")
    H.append(f"</main><script>{JS}</script></body></html>")
    os.makedirs(os.path.dirname(os.path.abspath(a.html)), exist_ok=True)
    open(a.html, "w").write("".join(H))
    with open(a.csv, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows_csv[0].keys()))
        w.writeheader(); w.writerows(rows_csv)
    print(f"{len(rows_csv)} versions -> {a.html} and {a.csv}")


if __name__ == "__main__":
    main()
