"""Build inter-argument relation files: for each debate, a CSV of
Support/Attack/Equivalent relations that link one argument to a *different*
argument (e.g. ARG-38_2012-T228 Attack ARG-38_2012-T229).

Source: data/annotations/relations/<debate>.ann (brat R lines).
Argument membership (T_id -> argument_id, possibly more than one argument
per T_id) is read from the already-built data/annotations/arguments/<debate>/*.csv.

Rules:
- Only relation types Support, Attack, Equivalent are considered.
- A relation is dropped if either endpoint isn't part of any argument
  (dead-end premise chains that never reach a root Claim).
- A relation is dropped if it only ever connects a component to itself
  (i.e. source and target argument are the same) -- these are the internal
  premise-chain edges already implicit within a single argument's CSV.
- A component can belong to more than one argument (a premise can support
  more than one claim); in that case the relation is emitted once per
  (source_argument, target_argument) pair, excluding same-argument pairs.
- Duplicate (relation_type, source_argument_id, target_argument_id) triples
  (e.g. two different premises of the same argument both attacking the same
  other argument) are collapsed into a single row.

Output: data/annotations/argument_relations/<debate>.csv, columns:
relation_type, source_argument_id, target_argument_id
"""
import csv
import glob
import os
import re
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ARGUMENTS_DIR = os.path.join(ROOT, "data", "annotations", "arguments")
RELATIONS_ANN_DIR = os.path.join(ROOT, "data", "annotations", "relations")
OUT_DIR = os.path.join(ROOT, "data", "annotations", "argument_relations")

RELATION_TYPES = {"Support", "Attack", "Equivalent"}
R_LINE_RE = re.compile(r"^R\d+\t(\w+) Arg1:(T\d+) Arg2:(T\d+)")

OUT_FIELDNAMES = ["relation_type", "source_argument_id", "target_argument_id"]


def parse_relations(path):
    relations = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            m = R_LINE_RE.match(line.rstrip("\n"))
            if m:
                rel_type, arg1, arg2 = m.groups()
                if rel_type in RELATION_TYPES:
                    relations.append((rel_type, arg1, arg2))
    return relations


def build_tid_to_arguments(debate_dir):
    tid_to_args = defaultdict(set)
    for path in glob.glob(os.path.join(debate_dir, "*.csv")):
        with open(path, newline="", encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                tid_to_args[row["T_id"]].add(row["argument_id"])
    return tid_to_args


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    debate_dirs = sorted(
        d for d in glob.glob(os.path.join(ARGUMENTS_DIR, "*")) if os.path.isdir(d)
    )
    print(f"Found {len(debate_dirs)} debate folders")

    total_rows = 0
    total_dropped_orphan = 0
    total_dropped_same_arg = 0
    total_dropped_duplicate = 0

    for debate_dir in debate_dirs:
        name = os.path.basename(debate_dir)
        ann_path = os.path.join(RELATIONS_ANN_DIR, f"{name}.ann")
        relations = parse_relations(ann_path)
        tid_to_args = build_tid_to_arguments(debate_dir)

        triples = set()
        for rel_type, arg1, arg2 in relations:
            args1 = tid_to_args.get(arg1, set())
            args2 = tid_to_args.get(arg2, set())
            if not args1 or not args2:
                total_dropped_orphan += 1
                continue
            for src_arg in args1:
                for tgt_arg in args2:
                    if src_arg == tgt_arg:
                        total_dropped_same_arg += 1
                        continue
                    triple = (rel_type, src_arg, tgt_arg)
                    if triple in triples:
                        total_dropped_duplicate += 1
                        continue
                    triples.add(triple)

        out_path = os.path.join(OUT_DIR, f"{name}.csv")
        with open(out_path, "w", newline="", encoding="utf-8") as fh:
            writer = csv.writer(fh)
            writer.writerow(OUT_FIELDNAMES)
            writer.writerows(sorted(triples))
        total_rows += len(triples)

    print(f"Wrote {total_rows} inter-argument relations to {OUT_DIR}")
    print(f"Dropped (orphan endpoint): {total_dropped_orphan}")
    print(f"Dropped (same-argument pair): {total_dropped_same_arg}")
    print(f"Dropped (duplicate triple): {total_dropped_duplicate}")


if __name__ == "__main__":
    main()
