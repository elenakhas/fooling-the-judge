"""Style features from open, published lexicons and tools (complements the project's family-E instrument).

Requires the lists built by fetch_lexicons.py (in $FTJ_DATA/lexicons) and:
  pip install convokit vaderSentiment empath spacy && python -m spacy download en_core_web_sm

open_features(text) -> dict of counts. Every feature records which published source it comes from (SOURCES).
Rates per 100 words are added by `with_rates(df)`.
"""
import os, re, warnings
warnings.filterwarnings("ignore")

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.environ.get("FTJ_DATA") or os.path.normpath(os.path.join(HERE, "..", "..", "data"))
LEX = os.path.join(DATA, "lexicons")

PHRASE_LISTS = {   # feature -> lexicon files (phrase matching, word boundaries, case-insensitive)
    "hedge_politeness": ["politeness_hedges"],
    "hedge_ulinski": ["hedges_ulinski"],
    "weakener_epistemic": ["ember_weakeners", "zhou_weakeners"],
    "strengthener_epistemic": ["ember_strengtheners", "zhou_strengtheners"],
    "connective_concession": ["dimlex_concession"],
    "connective_comparison": ["dimlex_comparison"],
}
WORD_LISTS = {"opinion_pos": ["opinion_positive"], "opinion_neg": ["opinion_negative"]}
EMPATH_CATS = ["positive_emotion", "negative_emotion", "sympathy", "affection", "politeness",
               "trust", "help", "optimism"]
CONVOKIT_KEEP = {"Hedges": "ck_hedges", "Factuality": "ck_factuality", "Deference": "ck_deference",
                 "Gratitude": "ck_gratitude", "Apologizing": "ck_apologizing", "Please": "ck_please",
                 "2nd_person": "ck_2nd_person", "1st_person": "ck_1st_person",
                 "HASPOSITIVE": "ck_haspositive", "HASNEGATIVE": "ck_hasnegative",
                 "Indirect_(greeting)": "ck_greeting", "SUBJUNCTIVE": "ck_subjunctive"}
SOURCES = {
    "hedge_politeness": "Yeomans et al. 2018 politeness package hedge list",
    "hedge_ulinski": "Ulinski, Benjamin & Hirschberg 2018, Table 1 (manual transcription)",
    "weakener_epistemic": "EMBER (Lee et al. 2025) + Zhou et al. 2023 weakeners",
    "strengthener_epistemic": "EMBER (Lee et al. 2025) + Zhou et al. 2023 strengtheners",
    "connective_concession": "DiMLex-Eng (Das et al. 2018), Comparison.Concession-dominant connectives",
    "connective_comparison": "DiMLex-Eng (Das et al. 2018), Comparison-dominant connectives",
    "opinion_pos / opinion_neg": "Hu & Liu 2004 opinion lexicon",
    "empath_*": "Empath (Fast et al. 2016)",
    "vader_*": "VADER (Hutto & Gilbert 2014)",
    "ck_*": "ConvoKit politeness strategies (Danescu-Niculescu-Mizil et al. 2013)",
}


def _load(name):
    p = os.path.join(LEX, f"{name}.txt")
    if not os.path.exists(p):
        return []
    return [l.strip().lower() for l in open(p) if l.strip()]


def _phrase_regex(terms):
    if not terms:
        return None
    pats = []
    for t in sorted(set(terms), key=len, reverse=True):
        esc = re.escape(t).replace(r"\*", r"\w*").replace(r"\ ", r"\s+").replace("'", "['’]")
        pats.append(esc)
    return re.compile(r"(?<![\w'])(?:" + "|".join(pats) + r")(?![\w'])", re.I)


_PHRASE = {f: _phrase_regex(sum((_load(n) for n in files), [])) for f, files in PHRASE_LISTS.items()}
_WORDS = {f: set(sum((_load(n) for n in files), [])) for f, files in WORD_LISTS.items()}
_TOKEN = re.compile(r"[a-z][a-z'\-]*")

_nlp = _ps = _empath = _vader = None


def _init_tools():
    global _nlp, _ps, _empath, _vader
    if _nlp is None:
        import spacy
        from convokit import PolitenessStrategies
        from empath import Empath
        from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
        _nlp = spacy.load("en_core_web_sm")
        _ps = PolitenessStrategies()
        _empath = Empath()
        _vader = SentimentIntensityAnalyzer()


def lexicon_status():
    """Which lists were found, with sizes (to report in the paper's methods)."""
    out = {f: sum(len(_load(n)) for n in files) for f, files in PHRASE_LISTS.items()}
    out.update({f: len(s) for f, s in _WORDS.items()})
    return out


def open_features(text, tools=True):
    text = (text or "").replace("’", "'")
    low = text.lower()
    toks = _TOKEN.findall(low)
    out = {"n_words": len(toks)}
    for f, rx in _PHRASE.items():
        out[f] = len(rx.findall(text)) if rx else None
    for f, words in _WORDS.items():
        out[f] = sum(t in words for t in toks) if words else None
    if tools:
        _init_tools()
        u = _ps.transform_utterance(text, spacy_nlp=_nlp)
        strat = u.meta["politeness_strategies"]
        for k, name in CONVOKIT_KEEP.items():
            out[name] = strat.get(f"feature_politeness_=={k}==", 0)
        emp = _empath.analyze(text, categories=EMPATH_CATS, normalize=False) or {}
        for c in EMPATH_CATS:
            out[f"empath_{c}"] = emp.get(c, 0)
        v = _vader.polarity_scores(text)
        out["vader_compound"], out["vader_pos"], out["vader_neg"] = v["compound"], v["pos"], v["neg"]
    return out


def with_rates(df, count_cols=None):
    """Add per-100-word rates for count columns."""
    count_cols = count_cols or [c for c in df.columns if c not in ("n_words",) and not c.startswith("vader_")]
    for c in count_cols:
        if c in df and df[c].notna().any():
            df[c + "_r100"] = 100 * df[c] / df["n_words"].clip(lower=1)
    return df


if __name__ == "__main__":
    import json, sys
    print(json.dumps(lexicon_status(), indent=1))
    demo = sys.argv[1] if len(sys.argv) > 1 else ("Great question! I can see why you'd think that, and you're not wrong "
            "in some contexts. However, in the usual setting the standard answer is clearly different.")
    print(json.dumps(open_features(demo), indent=1))
