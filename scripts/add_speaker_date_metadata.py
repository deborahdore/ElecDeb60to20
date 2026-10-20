"""Add `speaker` and `date` columns to every argument CSV under
data/annotations/arguments/.

- `date`: the debate's real-world date (ISO YYYY-MM-DD), the same for every
  row in a given debate folder. Verified against the historical record
  (moderator, venue, candidates present in each transcript) rather than
  data/full_debates.csv, which is incomplete/unreliable for this mapping.

- `speaker`: derived per row, by locating the row's text in the debate's
  transcript (data/annotations/txt/<debate>.txt) and taking the nearest
  preceding "NAME:" turn marker.

  For most rows the stored start_char/end_char line up exactly with the
  transcript. For a subset of debates (13_1988, 21_1992, 41_2016, 42_2016,
  43_2016 and small parts of a few others) the offsets don't match that
  transcript file, so as a fallback we search for the row's text directly
  (matching curly/straight quotes, en/em dashes, and whitespace runs
  loosely). If the text is found at exactly one location, that location is
  used. If the text can't be found, or is found at more than one location
  (e.g. short interjections like "Wrong" that repeat verbatim), speaker is
  left empty and the row is reported as unresolved rather than guessed.
"""
import csv
import glob
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ARGUMENTS_DIR = os.path.join(ROOT, "data", "annotations", "arguments")
TXT_DIR = os.path.join(ROOT, "data", "annotations", "txt")

TURN_RE = re.compile(r"(?m)^([A-Z][A-Z.\' ]{1,30}):\s")

# Verified against the historical record (moderator / venue / candidates
# present in each transcript), not derived from data/full_debates.csv.
DEBATE_DATES = {
    "1_1960": "1960-09-26", "2_1960": "1960-10-07", "3_1960": "1960-10-13", "4_1960": "1960-10-21",
    "5_1976": "1976-09-23", "6_1976": "1976-10-06", "7_1976": "1976-10-22",
    "8_1980": "1980-09-21", "9_1980": "1980-10-28",
    "10_1984": "1984-10-07", "11_1984": "1984-10-11", "12_1984": "1984-10-21",
    "13_1988": "1988-09-25", "14_1988": "1988-10-05", "15_1988": "1988-10-13",
    "16_1992": "1992-10-11", "17_1992": "1992-10-11", "18_1992": "1992-10-13",
    "19_1992": "1992-10-19", "20_1992": "1992-10-15", "21_1992": "1992-10-15",
    "22_1996": "1996-10-06", "23_1996": "1996-10-09", "24_1996": "1996-10-16",
    "25_2000": "2000-10-03", "26_2000": "2000-10-05", "27_2000": "2000-10-11", "28_2000": "2000-10-17",
    "29_2004": "2004-09-30", "30_2004": "2004-10-05", "31_2004": "2004-10-08", "32_2004": "2004-10-13",
    "33_2008": "2008-09-26", "34_2008": "2008-10-02", "35_2008": "2008-10-07", "36_2008": "2008-10-15",
    "37_2012": "2012-10-03", "38_2012": "2012-10-11", "39_2012": "2012-10-16", "40_2012": "2012-10-22",
    "41_2016": "2016-09-26", "42_2016": "2016-10-09", "43_2016": "2016-10-19",
    "44_2020": "2020-09-29", "45_2020": "2020-10-07", "46_2020": "2020-10-22",
}


def build_turns(text):
    return [(m.start(), m.group(1).strip()) for m in TURN_RE.finditer(text)]


def speaker_at(turns, offset):
    speaker = None
    for start, name in turns:
        if start <= offset:
            speaker = name
        else:
            break
    return speaker


def fuzzy_pattern(s):
    """Build a regex matching `s` loosely: any quote style, any dash run
    (-, --, ' -- '), and any whitespace run, exactly like the literal text
    otherwise."""
    parts = []
    i, n = 0, len(s)
    while i < n:
        ch = s[i]
        if ch in "'’‘":
            parts.append("['’‘]")
            i += 1
        elif ch in '"“”':
            parts.append('["“”]')
            i += 1
        elif ch == "-":
            parts.append(r"\s*-+\s*")
            i += 1
        elif ch.isspace():
            parts.append(r"\s+")
            i += 1
            while i < n and s[i].isspace():
                i += 1
        else:
            parts.append(re.escape(ch))
            i += 1
    return "".join(parts)


def locate(raw_text, row_text, start, end):
    if raw_text[start:end] == row_text:
        return start, end
    matches = list(re.finditer(fuzzy_pattern(row_text), raw_text))
    if len(matches) == 1:
        return matches[0].start(), matches[0].end()
    return None


def main():
    debate_dirs = sorted(
        d for d in glob.glob(os.path.join(ARGUMENTS_DIR, "*")) if os.path.isdir(d)
    )
    print(f"Found {len(debate_dirs)} debate folders")

    fieldnames = [
        "role", "text", "original_label", "T_id", "start_char", "end_char",
        "speaker", "date", "embedding",
    ]

    total_rows = 0
    unresolved = []
    for debate_dir in debate_dirs:
        name = os.path.basename(debate_dir)
        date = DEBATE_DATES[name]

        txt_path = os.path.join(TXT_DIR, f"{name}.txt")
        with open(txt_path, encoding="utf-8") as fh:
            raw_text = fh.read()
        turns = build_turns(raw_text)

        for path in glob.glob(os.path.join(debate_dir, "*.csv")):
            with open(path, newline="", encoding="utf-8") as fh:
                rows = list(csv.DictReader(fh))
            for row in rows:
                total_rows += 1
                loc = locate(raw_text, row["text"], int(row["start_char"]), int(row["end_char"]))
                if loc is None:
                    row["speaker"] = ""
                    unresolved.append((path, row["T_id"], row["role"]))
                else:
                    row["speaker"] = speaker_at(turns, loc[0]) or ""
                row["date"] = date
            with open(path, "w", newline="", encoding="utf-8") as fh:
                writer = csv.DictWriter(fh, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(rows)

    print(f"Updated {total_rows} rows across {len(debate_dirs)} debates")
    print(f"Unresolved speaker (left blank): {len(unresolved)} rows")
    if unresolved:
        out_path = os.path.join(ROOT, "scripts", "unresolved_speakers.csv")
        with open(out_path, "w", newline="", encoding="utf-8") as fh:
            writer = csv.writer(fh)
            writer.writerow(["file", "T_id", "role"])
            writer.writerows(unresolved)
        print(f"List of unresolved rows written to {out_path}")


if __name__ == "__main__":
    main()
