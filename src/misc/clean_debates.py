#!/usr/bin/env python3
"""
clean_debates.py
----------------
Cleans all .txt debate transcripts in a folder:
  1. Fixes mojibake (corrupted encoding) using ftfy + manual patterns
  2. Normalises Unicode punctuation to plain ASCII
  3. Removes non-breaking spaces, HTML &nbsp;, stray Â artifacts, stray ® symbols
  4. Collapses multiple spaces/tabs to one
  5. Removes spaces that crept in before punctuation (, ; : ! ?)
  6. Inserts a space after punctuation (, ; : ! ?) when one is missing
  7. Strips leading/trailing whitespace from each line

Output is written to <INPUT_DIR>/../txt_cleaned/ (created if absent).
The originals are never modified.

Usage:
    python3 clean_debates.py [input_dir]

    input_dir defaults to  ./data/annotations/txt
"""

import os
import re
import sys
import ftfy

# ── paths ──────────────────────────────────────────────────────────────────────
DEFAULT_INPUT = "/Users/ddore/Documents/ElecDeb60to20/data/annotations/txt"

def get_dirs(argv):
    input_dir = argv[1] if len(argv) > 1 else DEFAULT_INPUT
    input_dir = os.path.abspath(input_dir)
    parent    = os.path.dirname(input_dir)
    output_dir = os.path.join(parent, "txt_cleaned")
    return input_dir, output_dir


# ── cleaning pipeline ─────────────────────────────────────────────────────────

# Characters that should have a space after them (but not before)
PUNCT_NEED_SPACE_AFTER = re.compile(r'([,;:!?])([^\s\d"\')\-])')

# Space(s) before punctuation that should attach to the preceding word
SPACE_BEFORE_PUNCT = re.compile(r'\s+([,;:!?])')

# Multiple spaces / tabs (does NOT touch newlines)
MULTI_SPACE = re.compile(r'[ \t]{2,}')

# Remaining mojibake patterns that ftfy cannot fully resolve in these files:
#   Ï€  (U+00CF + U+20AC)  →  apostrophe  (e.g. "it's", "80's")
MOJIBAKE_APOS_1 = re.compile('\u00cf\u20ac')          # Ï + €
#   π  between two letters → apostrophe  (e.g. "itπs")
MOJIBAKE_APOS_2 = re.compile(r'(?<=[A-Za-z])\u03c0(?=[A-Za-z])')
#   ≥ / ≤  used as opening / closing quotation marks in one file
#   (U+2265 and U+2264 — never legitimate in debate transcripts)
MOJIBAKE_OPEN_QUOTE  = re.compile('\u2265')            # ≥
MOJIBAKE_CLOSE_QUOTE = re.compile('\u2264')            # ≤


def clean_text(text: str) -> str:
    # ── 1. ftfy: fix the bulk of encoding/mojibake issues ─────────────────────
    text = ftfy.fix_text(text)

    # ── 2. manual mojibake fixes not covered by ftfy ──────────────────────────
    text = MOJIBAKE_APOS_1.sub("'",  text)   # Ï€  → apostrophe
    text = MOJIBAKE_APOS_2.sub("'",  text)   # π   → apostrophe (between letters)
    text = MOJIBAKE_OPEN_QUOTE.sub('"',  text)  # ≥ → "
    text = MOJIBAKE_CLOSE_QUOTE.sub('"', text)  # ≤ → "

    # ── 3. normalise Unicode punctuation → plain ASCII ────────────────────────
    replacements = {
        '\u2019': "'",   # RIGHT SINGLE QUOTATION MARK  '
        '\u2018': "'",   # LEFT SINGLE QUOTATION MARK   '
        '\u201c': '"',   # LEFT DOUBLE QUOTATION MARK   "
        '\u201d': '"',   # RIGHT DOUBLE QUOTATION MARK  "
        '\u2014': '--',  # EM DASH                      —
        '\u2013': '-',   # EN DASH                      –
        '\u2026': '...',  # HORIZONTAL ELLIPSIS          …
        '\u00ad': '',    # SOFT HYPHEN (invisible)
        '\u009d': '',    # OPERATING SYSTEM COMMAND (control char, invisible)
        '\u00a0': ' ',   # NO-BREAK SPACE               → regular space
        '\u00ae': '',    # REGISTERED SIGN ® (artifact in these transcripts)
    }
    for src, dst in replacements.items():
        text = text.replace(src, dst)

    # ── 3b. HTML entity &nbsp; → space ────────────────────────────────────────
    text = text.replace('&nbsp;', ' ')

    # ── 3c. stray Â (U+00C2) left over from non-breaking-space mojibake ───────
    # Pattern: Â followed by a space (the \xa0 byte was already handled above
    # or was turned into a space, leaving a dangling Â).
    text = re.sub(r'\u00c2(?=\s)', '', text)
    # Also handle Â at end of token with no following space
    text = text.replace('\u00c2', '')

    # ── 4. collapse multiple spaces / tabs ────────────────────────────────────
    text = MULTI_SPACE.sub(' ', text)

    # ── 5. remove space(s) before punctuation ─────────────────────────────────
    text = SPACE_BEFORE_PUNCT.sub(r'\1', text)

    # ── 6. insert space after punctuation when missing ────────────────────────
    # Guard: do NOT add space if the next char is a digit (e.g. "1,000")
    #        or a closing bracket/quote, or a hyphen.
    text = PUNCT_NEED_SPACE_AFTER.sub(r'\1 \2', text)

    # ── 7. strip each line ────────────────────────────────────────────────────
    lines = text.split('\n')
    lines = [line.strip() for line in lines]
    text  = '\n'.join(lines)

    # ── 8. final collapse of any double-spaces introduced above ───────────────
    text = MULTI_SPACE.sub(' ', text)

    return text


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    input_dir, output_dir = get_dirs(sys.argv)

    if not os.path.isdir(input_dir):
        print(f"ERROR: input directory not found: {input_dir}")
        sys.exit(1)

    os.makedirs(output_dir, exist_ok=True)

    txt_files = sorted(f for f in os.listdir(input_dir) if f.endswith('.txt'))
    if not txt_files:
        print("No .txt files found.")
        sys.exit(0)

    print(f"Input  : {input_dir}  ({len(txt_files)} files)")
    print(f"Output : {output_dir}")
    print()

    changed = 0
    for fname in txt_files:
        in_path  = os.path.join(input_dir,  fname)
        out_path = os.path.join(output_dir, fname)

        with open(in_path, 'r', encoding='utf-8') as fh:
            original = fh.read()

        cleaned = clean_text(original)

        with open(out_path, 'w', encoding='utf-8') as fh:
            fh.write(cleaned)

        if cleaned != original:
            changed += 1
            # Count changes for the report
            orig_non_ascii = sum(1 for c in original if ord(c) > 127)
            new_non_ascii  = sum(1 for c in cleaned  if ord(c) > 127)
            orig_multi     = len(re.findall(r'[ \t]{2,}', original))
            new_multi      = len(re.findall(r'[ \t]{2,}', cleaned))
            print(f"  {fname}")
            print(f"    non-ASCII chars : {orig_non_ascii:>5}  →  {new_non_ascii}")
            print(f"    multi-spaces    : {orig_multi:>5}  →  {new_multi}")
        else:
            print(f"  {fname}  (no changes)")

    print()
    print(f"Done. {changed}/{len(txt_files)} files modified.")
    print(f"Cleaned files saved to: {output_dir}")


if __name__ == '__main__':
    main()
