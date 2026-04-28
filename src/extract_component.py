#!/usr/bin/env python3
"""
brat_to_conll.py
Convert brat .ann files + corresponding .txt files into BIO-tagged CoNLL format.

Input:
  - .ann files in ANN_DIR  (e.g. data/annotations/components/)
  - .txt files in TXT_DIR  (e.g. data/annotations/txt/)

Output:
  - one .conll file per .ann file, written to OUT_DIR (e.g. data/components/)

CoNLL format produced:
  token  _  _  B-Claim
  token  _  _  I-Claim
  token  _  _  O
  <blank line between speaker turns>

Rules:
  - Speaker label tokens (e.g. TRUMP:, CAROLE SIMPSON:) are skipped entirely.
  - A blank line is inserted before each new speaker's content.
  - Supported entity types: Claim, Premise  (extend ENTITY_TYPES to add more)
  - Handles discontinuous brat spans (e.g. "T1\tClaim 10 20;30 40\t...")
"""

import os
import re
import sys

# ── paths ────────────────────────────────────────────────────────────────────
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

ANN_DIR = os.path.join(BASE, "data", "annotations", "components")
TXT_DIR = os.path.join(BASE, "data", "annotations", "txt")
OUT_DIR = os.path.join(BASE, "data", "components", "conll")

ENTITY_TYPES = {"Claim", "Premise"}

# Speaker label detection (character-level, independent of tokenisation):
#   One or more ALL-CAPS words (letters, dots, hyphens) separated by single
#   spaces, immediately followed by ':'.
#   Examples: "TRUMP:"  "CAROLE SIMPSON:"  "GOVERNOR CARTER:"  "MR. FLECK:"
_SPKR_RE = re.compile(r"[A-Z][A-Z\.\-]*(?:\s+[A-Z][A-Z\.\-]*)*:")

# Punctuation-aware tokeniser pattern:
#   matches words (including contractions like "don't") OR single punctuation chars
_TOKEN_RE = re.compile(r"[A-Za-z0-9]+(?:'[A-Za-z]+)*|[^\w\s]")


# ── brat parser ──────────────────────────────────────────────────────────────
def parse_ann(ann_path):
    """
    Return a list of (label, [(start, end), ...]) sorted by first span start.
    Only T-lines (text-bound annotations) are parsed; relations etc. ignored.
    """
    annotations = []
    with open(ann_path, encoding="utf-8") as fh:
        for line in fh:
            line = line.rstrip("\n")
            if not line.startswith("T"):
                continue
            parts = line.split("\t", 2)
            if len(parts) < 2:
                continue
            tag_field = parts[1]  # e.g. "Claim 3116 3129" or "Claim 10 20;30 40"
            m = re.match(r"(\w+)\s+(.+)", tag_field)
            if not m:
                continue
            label = m.group(1)
            if label not in ENTITY_TYPES:
                continue
            # parse (possibly discontinuous) spans
            spans = []
            for seg in m.group(2).split(";"):
                seg = seg.strip()
                coords = seg.split()
                if len(coords) == 2:
                    spans.append((int(coords[0]), int(coords[1])))
            if spans:
                annotations.append((label, spans))

    # sort by the start of the first span
    annotations.sort(key=lambda x: x[1][0][0])
    return annotations


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
    A brat span can start at a punctuation character (e.g. the ';' in a
    run like '; to wonder').  After the initial BIO assignment, any B-X
    tag sitting on a punctuation-only token is wrong.  Fix it by:
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
        label = fixed[i][2:]  # e.g. "Claim"
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
def convert(ann_path, txt_path, out_path):
    annotations = parse_ann(ann_path)

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

    ann_files = sorted(f for f in os.listdir(ANN_DIR) if f.endswith(".ann"))
    if not ann_files:
        print(f"No .ann files found in {ANN_DIR}", file=sys.stderr)
        sys.exit(1)

    ok = skipped = 0
    for ann_file in ann_files:
        stem = ann_file[:-4]  # strip .ann
        txt_file = stem + ".txt"

        ann_path = os.path.join(ANN_DIR, ann_file)
        txt_path = os.path.join(TXT_DIR, txt_file)
        out_path = os.path.join(OUT_DIR, stem + ".conll")

        if not os.path.isfile(txt_path):
            print(f"  [SKIP] no matching .txt for {ann_file}")
            skipped += 1
            continue

        n_tok, n_ann = convert(ann_path, txt_path, out_path)
        print(f"  [OK]   {ann_file}  →  {stem}.conll  "
              f"({n_tok} tokens, {n_ann} annotations)", flush=True)
        ok += 1

    print(f"\nDone: {ok} converted, {skipped} skipped.")
    print(f"Output directory: {OUT_DIR}")


if __name__ == "__main__":
    main()
