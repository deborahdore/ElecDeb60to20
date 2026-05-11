"""
find_component_overlap.py

For each row in fallacies_with_spans.csv, check whether the fallacy overlaps
with any argument component (T-lines) in the corresponding .ann file under
data/annotations/relations/.

Two complementary strategies are tried in order:

  1. Span overlap (character-level):
       max(f_start, c_start) < min(f_end, c_end)
     Covers identical spans, fallacy ⊆ component, component ⊆ fallacy, and
     partial overlaps.

  2. Text similarity (fallback, used only when span overlap finds nothing):
     Both the fallacy text and the component text are normalised (lowercased,
     punctuation removed, whitespace collapsed) and then compared:
       a. One normalised text is a substring of the other, OR
       b. Levenshtein distance < MAX_EDIT_DIST (default 5).
     This catches cases where span positions are slightly off but the texts
     are the same or nearly the same.

Output columns (appended to input):
  component_id   — T-ID of the single best-matching component (lowest edit
                   distance between normalised fallacy text and normalised
                   component text), or empty string if none
  has_overlap    — True / False
  match_method   — "span", "text", or "" (no match)
"""

import csv
import os
import re

CSV_IN = "/Users/ddore/Documents/ElecDeb60to20/data/annotations/fallacies/fallacies_v2.csv"
ANN_DIR = "/Users/ddore/Documents/ElecDeb60to20/data/annotations/relations"
CSV_OUT = "/Users/ddore/Documents/ElecDeb60to20/data/annotations/fallacies/fallacies_v3.csv"

MAX_EDIT_DIST = 5  # strictly less-than threshold (edit distance < 5)


# ── Normalisation ─────────────────────────────────────────────────────────────

def _normalise(s: str) -> str:
    """Lowercase, strip punctuation, collapse whitespace."""
    # s = s.lower()
    s = re.sub(r'[^\w\s]', '', s)
    s = re.sub(r'\s+', ' ', s)
    return s.strip()


# ── Edit distance (bounded Levenshtein) ───────────────────────────────────────

def _levenshtein_bounded(s: str, t: str, max_dist: int) -> int:
    """
    Levenshtein distance between s and t, capped at max_dist + 1.
    Band-restricted DP: stops a row early if the minimum in that row already
    exceeds max_dist, giving O(len(s) * max_dist) in the common reject case.
    """
    if abs(len(s) - len(t)) > max_dist:
        return max_dist + 1
    if s == t:
        return 0
    m, n = len(s), len(t)
    dp = list(range(n + 1))
    for i in range(1, m + 1):
        new_dp = [i] + [0] * n
        row_min = i
        for j in range(1, n + 1):
            cost = 0 if s[i - 1] == t[j - 1] else 1
            new_dp[j] = min(new_dp[j - 1] + 1, dp[j] + 1, dp[j - 1] + cost)
            row_min = min(row_min, new_dp[j])
        if row_min > max_dist:
            return max_dist + 1
        dp = new_dp
    return dp[n]


# ── Parse .ann files ──────────────────────────────────────────────────────────

# Matches:  T123\tClaim 12345 67890\tsome text…
_T_LINE = re.compile(r'^(T\d+)\t\S+\s+(\d+)\s+(\d+)\t(.*)')

# Cache: filename → list of (tid, start, end, norm_text)
_ann_cache: dict[str, list[tuple[str, int, int, str]]] = {}


def load_ann(filename: str) -> list[tuple[str, int, int, str]]:
    """Return list of (component_id, start, end, norm_text) for every T-line."""
    if filename not in _ann_cache:
        path = os.path.join(ANN_DIR, filename + ".ann")
        components = []
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                m = _T_LINE.match(line.rstrip('\n'))
                if m:
                    tid = m.group(1)
                    start = int(m.group(2))
                    end = int(m.group(3))
                    norm_text = _normalise(m.group(4))
                    components.append((tid, start, end, norm_text))
        _ann_cache[filename] = components
    return _ann_cache[filename]


# ── Overlap strategies ────────────────────────────────────────────────────────

def _levenshtein(s: str, t: str) -> int:
    """Standard (unbounded) Levenshtein distance, used for ranking candidates."""
    m, n = len(s), len(t)
    dp = list(range(n + 1))
    for i in range(1, m + 1):
        new_dp = [i] + [0] * n
        for j in range(1, n + 1):
            cost = 0 if s[i - 1] == t[j - 1] else 1
            new_dp[j] = min(new_dp[j - 1] + 1, dp[j] + 1, dp[j - 1] + cost)
        dp = new_dp
    return dp[n]


def _best_candidate(
        fallacy_norm: str,
        candidates: list[tuple[str, str]],  # (tid, comp_norm)
) -> str:
    """Return the T-ID whose normalised text is closest to fallacy_norm."""
    return min(
        candidates,
        key=lambda x: _levenshtein(fallacy_norm, x[1]),
    )[0]


def by_span(
        f_start: int,
        f_end: int,
        components: list[tuple[str, int, int, str]],
) -> list[tuple[str, str]]:
    """Return (tid, norm_text) pairs for all components overlapping [f_start, f_end)."""
    return [
        (tid, comp_norm)
        for tid, c_start, c_end, comp_norm in components
        if max(f_start, c_start) < min(f_end, c_end)
    ]


def by_text(
        fallacy_norm: str,
        components: list[tuple[str, int, int, str]],
        max_dist: int = MAX_EDIT_DIST,
) -> list[tuple[str, str]]:
    """
    Return (tid, norm_text) pairs for components whose normalised text is
    similar to fallacy_norm (substring match OR edit distance < max_dist+1).
    """
    hits = []
    for tid, _, _, comp_norm in components:
        if not comp_norm:
            continue
        if fallacy_norm in comp_norm or comp_norm in fallacy_norm:
            hits.append((tid, comp_norm))
            continue
        dist = _levenshtein_bounded(fallacy_norm, comp_norm, max_dist)
        if dist <= max_dist:
            hits.append((tid, comp_norm))
    return hits


# ── Main ──────────────────────────────────────────────────────────────────────

stats = {"total": 0, "span": 0, "text": 0, "none": 0, "no_span": 0}

with open(CSV_IN, newline="", encoding="utf-8") as f_in, \
        open(CSV_OUT, "w", newline="", encoding="utf-8") as f_out:
    reader = csv.DictReader(f_in, delimiter=";")
    fieldnames = list(reader.fieldnames) + [
        "component_id", "has_overlap", "match_method"
    ]
    writer = csv.DictWriter(
        f_out, fieldnames=fieldnames, delimiter=";", extrasaction="ignore"
    )
    writer.writeheader()

    for row in reader:
        stats["total"] += 1
        found_span = row.get("span", "") or row.get("span", "")
        fallacy_text = row.get("text", "")

        if found_span in ("TEXT_NOT_FOUND", "FILE_NOT_FOUND", ""):
            row["component_id"] = ""
            row["has_overlap"] = "False"
            row["match_method"] = ""
            stats["no_span"] += 1
            writer.writerow(row)
            continue

        f_start, f_end = map(int, found_span.split())
        filename = row["filename"]

        try:
            components = load_ann(filename)
        except FileNotFoundError:
            row["component_id"] = "ANN_NOT_FOUND"
            row["has_overlap"] = "False"
            row["match_method"] = ""
            writer.writerow(row)
            continue

        fallacy_norm = _normalise(fallacy_text)

        # Strategy 1: span overlap → pick closest by edit distance
        candidates = by_span(f_start, f_end, components)
        method = "span" if candidates else ""

        # Strategy 2: text similarity fallback → pick closest by edit distance
        if not candidates:
            candidates = by_text(fallacy_norm, components)
            method = "text" if candidates else ""

        if candidates:
            best_id = _best_candidate(fallacy_norm, candidates)
            stats[method] += 1
        else:
            best_id = ""
            stats["none"] += 1

        row["component_id"] = best_id
        row["has_overlap"] = str(bool(best_id))
        row["match_method"] = method

        writer.writerow(row)

# ── Report ────────────────────────────────────────────────────────────────────
total = stats["total"]
print(f"Processed  : {total} rows")
print(f"Has overlap: {stats['span'] + stats['text']} "
      f"({100 * (stats['span'] + stats['text']) / total:.1f}%)")
print(f"  via span : {stats['span']}")
print(f"  via text : {stats['text']}")
print(f"No overlap : {stats['none']}")
print(f"No span    : {stats['no_span']}")
print(f"\nOutput → {CSV_OUT}")
