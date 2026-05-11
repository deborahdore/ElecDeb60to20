#!/usr/bin/env python3
"""
extract_fallacies.py
Convert fallacies CSV + corresponding .txt files into BIO-tagged CoNLL format.

Input:
  - fallacies CSV (CSV_PATH) with columns: filename, span, fallacy_type
  - .txt files in TXT_DIR  (e.g. data/annotations/txt/)

Output:
  - one .conll file per debate file that has fallacy annotations, written to OUT_DIR

CoNLL format produced:
  token  _  _  B-Ad_Hominem
  token  _  _  I-Ad_Hominem
  token  _  _  O
  <blank line between speaker turns>

Rules:
  - Speaker label tokens (e.g. TRUMP:, CAROLE SIMPSON:) are skipped entirely.
  - A blank line is inserted before each new speaker's content.
  - Fallacy type labels have spaces replaced with underscores (e.g. "Ad Hominem" → "Ad_Hominem").
  - When multiple fallacy spans overlap, the first-sorted span (by start char) wins.
"""

import csv
import os
import re
import sys
from collections import defaultdict

# ── paths ────────────────────────────────────────────────────────────────────
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

CSV_PATH = os.path.join(BASE, "data", "annotations", "fallacies", "fallacies_with_components_v2.csv")
TXT_DIR = os.path.join(BASE, "data", "annotations", "txt")
OUT_DIR = os.path.join(BASE, "data", "fallacies", "conll")

# Speaker label detection (character-level, independent of tokenisation):
#   One or more ALL-CAPS words (letters, dots, hyphens) separated by single
#   spaces, immediately followed by ':'.
#   Examples: "TRUMP:"  "CAROLE SIMPSON:"  "GOVERNOR CARTER:"  "MR. FLECK:"
_SPKR_RE = re.compile(r"[A-Z][A-Z\.\-]*(?:\s+[A-Z][A-Z\.\-]*)*:")

# Punctuation-aware tokeniser pattern:
#   matches words (including contractions like "don't") OR single punctuation chars
_TOKEN_RE = re.compile(r"[A-Za-z0-9]+(?:'[A-Za-z]+)*|[^\w\s]")


# ── CSV reader ───────────────────────────────────────────────────────────────
def load_fallacies(csv_path):
    """
    Read the fallacies CSV and return a dict:
      { filename: [(label, [(start, end)]), ...] }
    sorted by span start within each file.

    Fallacy type labels have spaces replaced with underscores.
    """
    groups = defaultdict(list)
    with open(csv_path, encoding="utf-8") as fh:
        reader = csv.DictReader(fh, delimiter=",")
        for row in reader:
            filename = row["source_filename"].strip()
            raw_label = row["fallacy"].strip()
            label = raw_label.replace(" ", "_")
            span_str = row["component_span"].strip()
            coords = span_str.split()
            if len(coords) != 2:
                continue
            try:
                start, end = int(coords[0]), int(coords[1])
            except ValueError:
                continue
            groups[filename].append((label, [(start, end)]))

    # Sort each file's annotations by the start of their span
    return {fn: sorted(anns, key=lambda x: x[1][0][0]) for fn, anns in groups.items()}


# ── tokeniser ────────────────────────────────────────────────────────────────
def tokenise(text):
    """
    Split text into tokens, separating punctuation from words.
    Returns (token, char_start, char_end) tuples; char_end is exclusive.

    Examples:
        "plan."   → [("plan", s, s+4), (".", s+4, s+5)]
        "don't"   → [("don't", s, s+5)]
        "(hello)" → [("(", s, s+1), ("hello", s+1, s+6), (")", s+6, s+7)]
    """
    return [(m.group(), m.start(), m.end()) for m in _TOKEN_RE.finditer(text)]


# ── span lookup (efficient) ──────────────────────────────────────────────────
def build_span_map(tokens, annotations):
    """
    Efficient O(text_length + n_annotations) BIO tagger.

    Strategy:
      1. Build a char-level array that records, for each character position,
         which annotation index covers it (and whether it is the first covered
         char of that annotation, so we can emit B- vs I-).
      2. Walk tokens once, looking up the first char of each token.
    """
    if not tokens:
        return []

    text_len = tokens[-1][2]  # end of last token

    # char_ann[i] = (ann_idx, is_begin) or None
    char_ann = [None] * text_len

    for ann_idx, (label, spans) in enumerate(annotations):
        first_char = spans[0][0]  # overall begin of this annotation
        for seg_start, seg_end in spans:
            for ci in range(seg_start, min(seg_end, text_len)):
                if char_ann[ci] is None:  # don't overwrite earlier annotations
                    char_ann[ci] = (ann_idx, ci == first_char)

    tags = []
    prev_ann_idx = None
    for tok, tok_start, tok_end in tokens:
        entry = char_ann[tok_start] if tok_start < text_len else None
        if entry is None:
            tags.append("O")
            prev_ann_idx = None
        else:
            ann_idx, is_begin = entry
            label = annotations[ann_idx][0]
            # Emit B- if this is the annotation's first character,
            # OR if we just jumped to a new annotation index.
            if is_begin or ann_idx != prev_ann_idx:
                tags.append(f"B-{label}")
            else:
                tags.append(f"I-{label}")
            prev_ann_idx = ann_idx

    return tags


# ── BIO punctuation fix ──────────────────────────────────────────────────────
_PUNCT_ONLY = re.compile(r"^[^\w]+$")  # token made entirely of non-word chars


def fix_begin_on_punct(tokens, tags):
    """
    A span can start at a punctuation character (e.g. the ';' in '; to wonder').
    After the initial BIO assignment, any B-X tag sitting on a punctuation-only
    token is wrong. Fix it by:
      - Setting the punctuation token to O.
      - Promoting the first following I-X token in the same span to B-X.
    The outer loop processes tokens left-to-right, so chained punctuation
    at the start of a span (e.g. '-- ;') is handled automatically.
    """
    fixed = list(tags)
    n = len(fixed)
    for i in range(n):
        if not fixed[i].startswith("B-"):
            continue
        tok = tokens[i][0]
        if not _PUNCT_ONLY.match(tok):
            continue  # B- on a real word → fine
        label = fixed[i][2:]  # e.g. "Ad_Hominem"
        fixed[i] = "O"
        # Promote the next I-label in the same span to B-
        for j in range(i + 1, n):
            if fixed[j] == f"I-{label}":
                fixed[j] = f"B-{label}"
                break
            elif fixed[j] == "O":
                break  # gap in annotation → stop
    return fixed


# ── speaker-label detector ───────────────────────────────────────────────────
def find_speaker_chars(text):
    """
    Return a set of character positions that belong to a speaker label,
    detected directly on the raw text (independent of tokenisation).

    A speaker label is one or more ALL-CAPS words followed immediately by ':'.
    Examples: "TRUMP:"  "CAROLE SIMPSON:"  "GOVERNOR CARTER:"  "MR. FLECK:"
    """
    speaker_chars = set()
    for m in _SPKR_RE.finditer(text):
        for ci in range(m.start(), m.end()):
            speaker_chars.add(ci)
    return speaker_chars


# ── converter ────────────────────────────────────────────────────────────────
def convert(annotations, txt_path, out_path):
    """
    Given a list of (label, [(start, end)]) annotations for one debate file,
    tokenise the txt, apply BIO tagging, and write the CoNLL output.
    """
    with open(txt_path, encoding="utf-8") as fh:
        text = fh.read()

    tokens = tokenise(text)
    tags = build_span_map(tokens, annotations)
    tags = fix_begin_on_punct(tokens, tags)
    speaker_chars = find_speaker_chars(text)

    with open(out_path, "w", encoding="utf-8") as fh:
        prev_was_speaker = False
        first_content = True
        skipped = 0
        for (tok, tok_start, _), tag in zip(tokens, tags):
            if tok_start in speaker_chars:
                prev_was_speaker = True
                skipped += 1
                continue
            if prev_was_speaker and not first_content:
                fh.write("\n")
            fh.write(f"{tok}\t_\t_\t{tag}\n")
            prev_was_speaker = False
            first_content = False

    return len(tokens) - skipped, len(annotations)


# ── main ─────────────────────────────────────────────────────────────────────
def main():
    os.makedirs(OUT_DIR, exist_ok=True)

    fallacies_by_file = load_fallacies(CSV_PATH)
    if not fallacies_by_file:
        print(f"No fallacy annotations found in {CSV_PATH}", file=sys.stderr)
        sys.exit(1)

    ok = skipped = 0
    for filename in sorted(fallacies_by_file):
        txt_file = filename + ".txt"
        txt_path = os.path.join(TXT_DIR, txt_file)
        out_path = os.path.join(OUT_DIR, filename + ".conll")

        if not os.path.isfile(txt_path):
            print(f"  [SKIP] no matching .txt for {filename}")
            skipped += 1
            continue

        annotations = fallacies_by_file[filename]
        n_tok, n_ann = convert(annotations, txt_path, out_path)
        print(f"  [OK]   {filename}  →  {filename}.conll  "
              f"({n_tok} tokens, {n_ann} annotations)", flush=True)
        ok += 1

    print(f"\nDone: {ok} converted, {skipped} skipped.")
    print(f"Output directory: {OUT_DIR}")


if __name__ == "__main__":
    main()
