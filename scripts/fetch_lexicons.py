"""Fetch and build the open lexicons used by features_open.py.

  python3 -I fetch_lexicons.py            # uses $FTJ_DATA (default ../../data)

Clones (if missing) into $FTJ_DATA/repos and writes plain-text lists to $FTJ_DATA/lexicons, plus
MANIFEST.json with source, licence, citation and size of every list. Needs: git, `pip install rdata`.

Lists built
  ember_strengtheners / ember_weakeners   markers inserted in EMBER (sampled from Zhou et al.'s in-the-wild LLM
                                          marker distribution)                       code licence: see repo
  zhou_strengtheners / zhou_weakeners     Zhou, Jurafsky & Hashimoto (2023) epistemic-marker templates
  politeness_hedges                       Yeomans et al. `politeness` R package hedge list (MIT)
  opinion_positive / opinion_negative     Hu & Liu (2004) opinion lexicon, as shipped in `politeness` (MIT pkg)
  dimlex_concession / dimlex_contrast     DiMLex-Eng (Das et al. 2018) connectives whose PDTB senses are mostly
                                          Comparison.Concession / Comparison.Contrast (CC BY-NC-SA 4.0)
Manual (not fetched)
  hedges_ulinski.txt                      117 terms from Table 1 of Ulinski, Benjamin & Hirschberg (2018);
                                          transcribe one term per line, if you want this list.
Runtime libraries (pip), not lists: convokit politeness strategies, vaderSentiment, empath.
"""
import collections, csv, glob, json, os, re, subprocess, sys
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.environ.get("FTJ_DATA") or os.path.normpath(os.path.join(HERE, "..", "..", "data"))
REPOS, LEX = os.path.join(DATA, "repos"), os.path.join(DATA, "lexicons")
os.makedirs(REPOS, exist_ok=True); os.makedirs(LEX, exist_ok=True)

SOURCES = {
    "EMBER": "https://github.com/DongryeolLee96/EMBER",
    "navigating_the_grey": "https://github.com/katezhou/navigating_the_grey",
    "politeness": "https://github.com/myeomans/politeness",
    "en_dimlex": "https://github.com/discourse-lab/en_dimlex",
}
manifest = {}


def clone(name):
    path = os.path.join(REPOS, name)
    if not os.path.exists(path):
        subprocess.run(["git", "clone", "-q", "--depth", "1", SOURCES[name], path], check=True)
    return path


def write(name, items, source, licence, citation, note=""):
    items = sorted({re.sub(r"\s+", " ", i.strip().lower()) for i in items if i and i.strip()})
    with open(os.path.join(LEX, f"{name}.txt"), "w") as f:
        f.write("\n".join(items) + "\n")
    manifest[name] = dict(n=len(items), source=source, licence=licence, citation=citation, note=note)
    print(f"{name:22s} {len(items):5d}")


# --- EMBER markers ---------------------------------------------------------------------------
p = clone("EMBER")
strong, weak = set(), set()
for fn in glob.glob(os.path.join(p, "datasets", "**", "*.json"), recursive=True):
    data = json.load(open(fn))
    for r in data if isinstance(data, list) else data.values():
        if isinstance(r, dict):
            for k, dst in (("str", strong), ("weak", weak)):
                v = r.get(k)
                if isinstance(v, str):
                    dst.add(v.strip(" .,:;!\"'"))
cit = "Lee et al. 2025, Are LLM-Judges Robust to Expressions of Uncertainty? (EMBER), NAACL"
write("ember_strengtheners", strong, SOURCES["EMBER"], "see repo", cit)
write("ember_weakeners", weak, SOURCES["EMBER"], "see repo", cit)

# --- Zhou et al. templates ---------------------------------------------------------------------
p = clone("navigating_the_grey")
strong, weak = set(), set()
TRAIL = re.compile(r"\s+(it'?s|it is|it was|that it'?s|that it is|be|is)$", re.I)
for r in csv.DictReader(open(os.path.join(p, "uncertainty_template_meta.csv"))):
    phrase = TRAIL.sub("", r["name"].strip())
    (strong if r["booster"] == "booster" else weak if r["booster"] == "hedge" else set()).add(phrase)
cit = "Zhou, Jurafsky & Hashimoto 2023, Navigating the Grey Area, EMNLP"
note = "sentence-initial templates with trailing 'it's/be' removed; low recall on free text"
write("zhou_strengtheners", strong, SOURCES["navigating_the_grey"], "see repo", cit, note)
write("zhou_weakeners", weak, SOURCES["navigating_the_grey"], "see repo", cit, note)

# --- politeness R package dictionaries ---------------------------------------------------------
p = clone("politeness")
try:
    import warnings, rdata
    warnings.filterwarnings("ignore")
    d = rdata.read_rda(os.path.join(p, "R", "sysdata.rda"))
    cit = "Yeomans, Kantor & Tingley 2018, Detecting Politeness in Natural Language, R Journal"
    write("politeness_hedges", [str(x) for x in d["hedge_list"]], SOURCES["politeness"], "MIT", cit,
          "entries may contain '*' wildcards")
    cit2 = "Hu & Liu 2004, Mining and Summarizing Customer Reviews, KDD (via politeness package)"
    write("opinion_positive", [str(x) for x in d["positive_list"]], SOURCES["politeness"], "MIT (package)", cit2)
    write("opinion_negative", [str(x) for x in d["negative_list"]], SOURCES["politeness"], "MIT (package)", cit2)
except ImportError:
    print("skip politeness lists: pip install rdata", file=sys.stderr)

# --- DiMLex-Eng connectives ---------------------------------------------------------------------
p = clone("en_dimlex")
root = ET.parse(os.path.join(p, "en_dimlex.xml")).getroot()
sense_freq = collections.defaultdict(collections.Counter)
for e in root.findall("entry"):
    w = e.get("word")
    for rel in e.iter():
        if rel.tag.endswith("_relation") and rel.get("sense"):
            top = ".".join(rel.get("sense").split(".")[:2])
            sense_freq[w][top] += int(rel.get("pdtb_freq") or 1)
cit = "Das, Scheffler, Bourgonje & Stede 2018, Constructing a Lexicon of English Discourse Connectives, SIGDIAL"
for label, keys in (("dimlex_concession", ("Comparison.Concession",)), ("dimlex_contrast", ("Comparison.Contrast",)),
                    ("dimlex_comparison", ("Comparison", "Comparison.Concession", "Comparison.Contrast",
                                           "Comparison.Pragmatic concession", "Comparison.Pragmatic contrast"))):
    keep = [w for w, c in sense_freq.items() if c and sum(c[k] for k in keys) / sum(c.values()) >= 0.5]
    write(label, keep, SOURCES["en_dimlex"], "CC BY-NC-SA 4.0", cit,
          f"connectives whose PDTB-frequency share for {'/'.join(keys)} is >= 50%")

# --- manual list ------------------------------------------------------------------------------------
ul = os.path.join(LEX, "hedges_ulinski.txt")
manifest["hedges_ulinski"] = dict(
    n=sum(1 for l in open(ul) if l.strip()) if os.path.exists(ul) else 0,
    source="Table 1, Ulinski, Benjamin & Hirschberg 2018 (W18-1301)", licence="paper",
    citation="Ulinski et al. 2018, Using Hedge Detection to Improve Committed Belief Tagging, SemBEaR",
    note="manual transcription; 117 terms expected" if not os.path.exists(ul) else "user-supplied")

json.dump(manifest, open(os.path.join(LEX, "MANIFEST.json"), "w"), indent=2)
print(f"\nwrote {len(manifest)} entries to {LEX}/MANIFEST.json")
