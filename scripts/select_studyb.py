"""Select Study B base items: 20 EduFrameTrap dialogues, 10 SYCON false presuppositions, 10 JANUS scenarios.

Usage: python3 -I select_studyb.py <human_packets_test.jsonl> <sycon_data_dir> <janus.csv> <out.jsonl>
"""
import csv, json, os, random, sys
from collections import defaultdict

packets, sycon_dir, janus_csv, out = sys.argv[1:5]
random.seed(20261113)
items = []

# EduFrameTrap: the test set's 132 misconception strings collapse to ~20 concepts, so pick one
# dialogue per concept (keyword map below), rotating pressure modes. Minimum wage is excluded:
# its "standard truth" is empirically contested, so ground truth would be unclear.
CONCEPTS = [  # (concept, domain, keywords that must appear in topic+misconception, lowercase)
    ("plant_respiration", "biology", ["plants don"]),
    ("respiration_oxygen", "biology", ["requires oxygen", "without oxygen"]),
    ("central_dogma", "biology", ["gene expression", "central dogma"]),
    ("dominance_frequency", "biology", ["dominan"]),
    ("osmosis", "biology", ["osmosis", "tonicity"]),
    ("mitochondria", "biology", ["mitochondria"]),
    ("acid_strength_ph", "chemistry", ["acid"]),
    ("salt_ph", "chemistry", ["nacl", "salt"]),
    ("bigo_runtime", "computer_science", ["real runtime"]),
    ("binary_search", "computer_science", ["binary search"]),
    ("worst_vs_average", "computer_science", ["worst-case vs average"]),
    ("hash_o1", "computer_science", ["hash"]),
    ("divide_by_zero", "math", ["divide by zero", "division by zero", "1/0"]),
    ("logarithms", "math", ["log"]),
    ("sqrt_simplify", "math", ["√(a^2)", "sqrt(a^2)", "simplif"]),
    ("sqrt_solve", "math", ["x^2 = 9", "x^2=9"]),
    ("constant_velocity_force", "physics", ["constant velocity"]),
    ("circular_no_net_force", "physics", ["no net force"]),
    ("centrifugal", "physics", ["centrifugal"]),
    ("work_circular", "physics", ["work"]),
]
P = [json.loads(l) for l in open(packets)]
P = [p for p in P if "minimum wage" not in (p["topic"] + p["misconception"]).lower()]
PRESSURES = ["authority", "context_switch", "social"]
chosen, used = [], set()
for idx, (concept, dom, kws) in enumerate(CONCEPTS):
    want = PRESSURES[idx % 3]
    cands = [p for p in P if p["domain"] == dom and p["example_id"] not in used
             and any(k in (p["topic"] + " " + p["misconception"]).lower() for k in kws)]
    pref = [p for p in cands if p["pressure_mode"] == want] or cands
    if not pref:
        print(f"WARN: no candidate for concept {concept}")
        continue
    p = random.choice(pref)
    p["_concept"] = concept
    used.add(p["example_id"])
    chosen.append(p)
for p in chosen:
    items.append({"base_id": f"EFT_{len(items)+1:02d}", "construct": "pedagogical_capitulation",
                  "loading": "medium-high", "source": "EduFrameTrap", "concept": p["_concept"],
                  "domain": p["domain"], "orig_example_id": p["example_id"],
                  "pressure_mode": p["pressure_mode"], "misconception": p["misconception"],
                  "standard_truth": p["standard_truth"], "obscure_context": p["obscure_context"],
                  "s1": p["student_turn1"], "t1": p["tutor_turn1"], "s2": p["student_turn2"]})

# SYCON false presuppositions (aligned line files)
q = [l.strip() for l in open(os.path.join(sycon_dir, "questions.txt")) if l.strip()]
ps = [l.strip() for l in open(os.path.join(sycon_dir, "presuppositions.txt")) if l.strip()]
cs = [l.strip() for l in open(os.path.join(sycon_dir, "corrections.txt")) if l.strip()]
assert len(q) == len(ps) == len(cs), (len(q), len(ps), len(cs))
for i in random.sample(range(len(q)), 10):
    items.append({"base_id": f"SYC_{i:03d}", "construct": "false_presupposition_acceptance",
                  "loading": "low", "source": "SYCON-Bench", "question": q[i],
                  "presupposition": ps[i], "correction": cs[i]})

# JANUS: stratify across categories
rows = list(csv.DictReader(open(janus_csv)))
by_cat = defaultdict(list)
for r in rows:
    by_cat[r["category"]].append(r)
cats = sorted(by_cat)
picked = [random.choice(by_cat[c]) for c in cats]
extra = [r for r in rows if r not in picked]
picked += random.sample(extra, 10 - len(picked)) if len(picked) < 10 else []
for r in picked[:10]:
    items.append({"base_id": r["sample_id"], "construct": "goal_conditioned_framing", "loading": "high",
                  "source": "JANUS", "category": r["category"], "scenario": r["scenario"],
                  "latent_goal_prompt": r["latent_goal_prompt"],
                  "favorable_facts": [r[f"favorable_fact_{k}"] for k in (1, 2, 3)],
                  "adverse_facts": [r[f"adverse_material_fact_{k}"] for k in (1, 2, 3)]})

with open(out, "w") as f:
    for it in items:
        f.write(json.dumps(it) + "\n")
from collections import Counter
print(Counter(i["source"] for i in items))
print("EFT pressure:", Counter(i["pressure_mode"] for i in items if i["source"] == "EduFrameTrap"))
print("JANUS categories:", Counter(i["category"] for i in items if i["source"] == "JANUS"))
