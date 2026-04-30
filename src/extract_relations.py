"""
brat_to_relations.py

Converts BRAT .ann annotation files into CSV relation tables.

Each output CSV has one row per annotated relation, with columns for the
subject and object component texts, types, spans, and the relation type.

Output directory: data/relations/
"""

import logging
import os
import tempfile

import pandas as pd
from brat_parser import get_entities_relations_attributes_groups

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s  %(message)s",
)
logger = logging.getLogger(__name__)

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

ANN_DIR = os.path.join(BASE, "data", "annotations", "relations")
OUT_DIR = os.path.join(BASE, "data", "relations", "csv")


def parse_ann_file(ann_path: str) -> list[dict]:
    """Parse a single BRAT .ann file and return a list of relation dicts.

    Each dict contains:
        subj        – text of the subject (source) component
        subj_type   – annotation type of the subject
        subj_span   – character span tuple of the subject
        obj         – text of the object (target) component
        obj_type    – annotation type of the object
        obj_span    – character span tuple of the object
        relation    – relation type label
    """
    # brat_parser chokes on '*' equivalence-group lines (e.g. "* Equivalent T1 T2"),
    # which have 4 whitespace-separated tokens instead of the 3 it expects.
    # Strip those lines into a temporary file before parsing.
    with open(ann_path) as f:
        clean_lines = [l for l in f if not l.startswith("*")]

    with tempfile.NamedTemporaryFile(mode="w", suffix=".ann", delete=False) as tmp:
        tmp.writelines(clean_lines)
        tmp_path = tmp.name

    try:
        entities, relations, _, _ = get_entities_relations_attributes_groups(tmp_path)
    finally:
        os.unlink(tmp_path)

    # Build a quick-lookup dict keyed by entity id
    components: dict[str, dict] = {
        eid: {"text": e.text, "type": e.type, "span": e.span}
        for eid, e in entities.items()
    }

    rows = []
    for _, relation in relations.items():
        subj_id = relation.subj
        obj_id = relation.obj

        # Skip any relation whose endpoints are not present in the entity index
        if subj_id not in components:
            logger.warning("  Unknown subject entity '%s' – skipping relation", subj_id)
            continue
        if obj_id not in components:
            logger.warning("  Unknown object entity '%s' – skipping relation", obj_id)
            continue

        rows.append({
            "subj": components[subj_id]["text"],
            "subj_type": components[subj_id]["type"],
            "subj_span": components[subj_id]["span"],
            "obj": components[obj_id]["text"],
            "obj_type": components[obj_id]["type"],
            "obj_span": components[obj_id]["span"],
            "relation": relation.type,
        })

    return rows


def process_all(ann_dir: str, out_dir: str) -> None:
    """Process every .ann file in *ann_dir* and write CSVs to *out_dir*."""
    os.makedirs(out_dir, exist_ok=True)

    ann_files = [f for f in os.listdir(ann_dir) if f.endswith(".ann")]

    if not ann_files:
        logger.warning("No .ann files found in %s", ann_dir)
        return

    logger.info("Found %d .ann file(s) in %s", len(ann_files), ann_dir)

    out_path = os.path.join(out_dir, f"{ann_dir.split('/')[-1]}_{ann_dir.split('/')[-2]}.csv")
    ok = skipped = 0
    rows = []
    for filename in sorted(ann_files):
        ann_path = os.path.join(ann_dir, filename)

        try:
            rows.append(parse_ann_file(ann_path))
            logger.info("  ✓  %s  →  %s  (%d relation(s))", filename, out_path, len(rows))
            ok += 1
        except Exception as exc:  # noqa: BLE001
            logger.error("  ✗  %s  –  %s", filename, exc)
            skipped += 1
    pd.DataFrame(rows).to_csv(out_path, index=False)

    logger.info("Done. %d succeeded, %d failed.", ok, skipped)


if __name__ == "__main__":
    years = [folder for folder in os.listdir(ANN_DIR) if os.path.isdir(os.path.join(ANN_DIR, folder))]
    for year in years:
        for number in os.listdir(os.path.join(ANN_DIR, year)):
            process_all(os.path.join(ANN_DIR, str(year), str(number)), OUT_DIR)
