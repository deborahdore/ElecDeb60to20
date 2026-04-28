"""
find_spans.py

For each row in fallacies.csv, find the correct character span of the "text"
field within the .txt file named by the "filename" field.

All matching is case-insensitive and punctuation-insensitive: both the search
text and the file content are normalised (lowercased, punctuation stripped,
whitespace collapsed) before comparison. Matched positions are then mapped
back to the original (un-normalised) character offsets.

Match strategy (tried in order until one succeeds):
  1. Exact match on normalised text.
  2. Full word-anchor regex: every word joined by \\W{1,MAX_GAP}, already
     case/punct-insensitive via re.IGNORECASE and \\W.
  3. Start + End anchor: first ANCHOR_N words pin the start, last N words
     (shrinking to MIN_ANCHOR) pin the end.  Handles mid-text word swaps.
  4. Edit-distance (Levenshtein < MAX_EDIT_DIST on normalised text): sliding
     window over word boundaries with bounded DP (stops early when distance
     already exceeds threshold).

Disambiguation (multiple candidates):
  a. Keep only spans where the nearest preceding speaker label matches the
     "speaker" field.
  b. Fall back to first candidate.

Output: fallacies_with_spans.csv  (same columns + "span": "start end")
  - "TEXT_NOT_FOUND"  if no match at all
  - "FILE_NOT_FOUND"  if the .txt file is missing
"""

import csv
import re
import os

CSV_PATH = "/Users/ddore/Documents/ElecDeb60to20/data/annotations/fallacies/fallacies.csv"
TXT_DIR  = "/Users/ddore/Documents/ElecDeb60to20/data/annotations/txt"
OUT_PATH = "/Users/ddore/Documents/ElecDeb60to20/data/annotations/fallacies/fallacies_v2.csv"

ANCHOR_N      = 6    # words used for start/end anchors
MIN_ANCHOR    = 3    # minimum anchor size when shrinking
MAX_GAP       = 50   # max non-word chars allowed between consecutive words
MAX_EDIT_DIST = 4    # maximum Levenshtein distance (edit distance < 5)


# ── Normalisation ─────────────────────────────────────────────────────────────

def _normalise(s: str) -> str:
    """Lowercase, strip punctuation, collapse whitespace."""
    # s = s.lower()
    s = re.sub(r'[^\w\s]', '', s)   # remove punctuation
    s = re.sub(r'\s+', ' ', s)       # collapse whitespace
    return s.strip()


def _build_norm_map(content: str) -> tuple[str, list[int]]:
    """
    Return (norm_content, orig_positions) where orig_positions[i] is the index
    in `content` of the i-th character of norm_content.

    Used to map a match on the normalised string back to the original offsets.
    """
    norm_chars: list[str] = []
    orig_pos:   list[int] = []
    prev_space = True  # avoids leading space
    for i, c in enumerate(content):
        lc = c
        # lc = c.lower()
        if lc.isalnum() or lc == '_':
            norm_chars.append(lc)
            orig_pos.append(i)
            prev_space = False
        elif c.isspace() or not lc.isalnum():
            if not prev_space and (c.isspace()):
                norm_chars.append(' ')
                orig_pos.append(i)
                prev_space = True
    return ''.join(norm_chars), orig_pos


_norm_cache:     dict[str, tuple[str, list[int]]] = {}
_content_cache:  dict[str, str] = {}


def load_file(filename: str) -> str:
    if filename not in _content_cache:
        path = os.path.join(TXT_DIR, filename + ".txt")
        with open(path, encoding="utf-8") as fh:
            _content_cache[filename] = fh.read()
    return _content_cache[filename]


def load_norm(filename: str) -> tuple[str, list[int]]:
    if filename not in _norm_cache:
        content = load_file(filename)
        _norm_cache[filename] = _build_norm_map(content)
    return _norm_cache[filename]


# ── Span helpers ──────────────────────────────────────────────────────────────

def _norm_to_orig_span(
    norm_start: int,
    norm_end: int,
    orig_positions: list[int],
    content: str,
) -> tuple[int, int]:
    """
    Convert a [norm_start, norm_end) span in normalised text to an
    [orig_start, orig_end) span in the original content.
    orig_end is advanced past any trailing punctuation/whitespace so the
    span closely mirrors the original phrasing.
    """
    orig_start = orig_positions[norm_start]
    # Last alphanumeric char in original
    orig_last  = orig_positions[min(norm_end - 1, len(orig_positions) - 1)]
    # Advance to end of the word/token
    orig_end = orig_last + 1
    while orig_end < len(content) and not content[orig_end].isspace():
        orig_end += 1
    return orig_start, orig_end


# ── Speaker detection ─────────────────────────────────────────────────────────

_SPEAKER_RE = re.compile(r'\n([A-Z][A-Z\s\.]+):', re.MULTILINE)
_speaker_index_cache: dict[str, list] = {}


def _build_speaker_index(filename: str, content: str) -> list[tuple[int, str]]:
    if filename not in _speaker_index_cache:
        _speaker_index_cache[filename] = [
            (m.end(), m.group(1).strip())
            for m in _SPEAKER_RE.finditer(content)
        ]
    return _speaker_index_cache[filename]


def get_speaker_at(filename: str, content: str, pos: int) -> str:
    index = _build_speaker_index(filename, content)
    speaker = ""
    for end_pos, name in index:
        if end_pos <= pos:
            speaker = name
        else:
            break
    return speaker


# ── Candidate picking ─────────────────────────────────────────────────────────

def pick_best(
    candidates: list[tuple[int, int]],
    filename: str,
    content: str,
    speaker: str,
) -> tuple[int, int]:
    if len(candidates) == 1:
        return candidates[0]
    speaker_norm = speaker.strip().upper()
    hits = [
        span for span in candidates
        if get_speaker_at(filename, content, span[0]).upper() == speaker_norm
    ]
    return hits[0] if hits else candidates[0]


# ── Edit distance (bounded Levenshtein) ───────────────────────────────────────

def _levenshtein_bounded(s: str, t: str, max_dist: int) -> int:
    """
    Levenshtein distance between s and t, capped at max_dist + 1.
    Uses a band-restricted DP: only computes cells within max_dist of the
    diagonal, making each call O(len(s) * max_dist) instead of O(len(s)*len(t)).
    """
    if abs(len(s) - len(t)) > max_dist:
        return max_dist + 1
    if s == t:
        return 0
    m, n = len(s), len(t)
    # Standard DP with early-row pruning
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


# ── Match strategies ──────────────────────────────────────────────────────────

def _word_pattern(words: list[str], max_gap: int = MAX_GAP) -> str:
    return (r'\W{1,' + str(max_gap) + r'}').join(re.escape(w) for w in words)


def strategy_exact(
    content: str, filename: str, text: str
) -> list[tuple[int, int]]:
    """Exact match on normalised text, mapped back to original offsets."""
    norm_content, orig_pos = load_norm(filename)
    norm_text = _normalise(text)
    results, start = [], 0
    while True:
        idx = norm_content.find(norm_text, start)
        if idx == -1:
            break
        orig_start, orig_end = _norm_to_orig_span(
            idx, idx + len(norm_text), orig_pos, content
        )
        results.append((orig_start, orig_end))
        start = idx + 1
    return results


def strategy_full_word_anchor(
    content: str, filename: str, text: str
) -> list[tuple[int, int]]:
    """All words joined by \\W{1,MAX_GAP}, case- and punct-insensitive."""
    words = re.findall(r'\w+', text)
    if not words:
        return []
    pattern = _word_pattern(words)
    return [
        (m.start(), m.end())
        for m in re.finditer(pattern, content, re.IGNORECASE)
    ]


def strategy_start_end_anchor(
    content: str, filename: str, text: str
) -> list[tuple[int, int]]:
    """First ANCHOR_N words fix start, last N words fix end."""
    words = re.findall(r'\w+', text)
    if len(words) < MIN_ANCHOR * 2:
        return []

    n_start = min(ANCHOR_N, len(words) // 2)
    start_pat = _word_pattern(words[:n_start])
    start_matches = list(re.finditer(start_pat, content, re.IGNORECASE))
    if not start_matches:
        return []

    results = []
    for sm in start_matches:
        for n_end in range(min(ANCHOR_N, len(words) - n_start), MIN_ANCHOR - 1, -1):
            end_pat = _word_pattern(words[-n_end:])
            em = re.search(end_pat, content[sm.start():], re.IGNORECASE)
            if em:
                results.append((sm.start(), sm.start() + em.end()))
                break
    return results


def strategy_edit_distance(
    content: str, filename: str, text: str,
    max_dist: int = MAX_EDIT_DIST,
) -> list[tuple[int, int]]:
    """
    Sliding-window Levenshtein on normalised text.

    Anchors the window at each word boundary in the normalised content to
    keep the search tractable.  Returns all windows whose edit distance to
    the normalised search text is < max_dist, mapped back to original offsets.
    """
    norm_content, orig_pos = load_norm(filename)
    norm_text = _normalise(text)
    L = len(norm_text)
    if L == 0 or len(norm_content) < L - max_dist:
        return []

    # Word-boundary start positions in normalised content
    word_starts = [0] + [
        m.start()
        for m in re.finditer(r'(?<= )\w', norm_content)
    ]

    best_dist = max_dist     # strictly less-than threshold
    results: list[tuple[int, int, int]] = []  # (orig_start, orig_end, dist)

    for ws in word_starts:
        # Check window sizes L ± max_dist (char-level slack)
        for win_len in range(max(1, L - max_dist), L + max_dist + 1):
            end = ws + win_len
            if end > len(norm_content):
                break
            window = norm_content[ws:end]
            dist = _levenshtein_bounded(norm_text, window, max_dist)
            if dist <= best_dist:
                orig_start, orig_end = _norm_to_orig_span(
                    ws, end, orig_pos, content
                )
                results.append((orig_start, orig_end, dist))
                if dist < best_dist:
                    best_dist = dist

    if not results:
        return []

    # Keep only the matches with the minimum observed distance
    min_dist = min(r[2] for r in results)
    return [(s, e) for s, e, d in results if d == min_dist]


# ── Top-level span finder ─────────────────────────────────────────────────────

def find_span(
    content: str,
    filename: str,
    text: str,
    speaker: str,
) -> tuple[int, int] | None:
    strategies = (
        strategy_exact,
        strategy_full_word_anchor,
        strategy_start_end_anchor,
        strategy_edit_distance,
    )
    for strategy in strategies:
        candidates = strategy(content, filename, text)
        if candidates:
            return pick_best(candidates, filename, content, speaker)
    return None


# ── Main ──────────────────────────────────────────────────────────────────────

not_found_rows = []
strategy_used: dict[str, int] = {
    "exact": 0, "word_anchor": 0, "start_end": 0, "edit_dist": 0
}


def find_span_with_stats(
    content: str, filename: str, text: str, speaker: str
) -> tuple[tuple[int, int] | None, str]:
    """Like find_span but also reports which strategy succeeded."""
    for name, strategy in [
        ("exact",       strategy_exact),
        ("word_anchor", strategy_full_word_anchor),
        ("start_end",   strategy_start_end_anchor),
        ("edit_dist",   strategy_edit_distance),
    ]:
        candidates = strategy(content, filename, text)
        if candidates:
            return pick_best(candidates, filename, content, speaker), name
    return None, "none"


with open(CSV_PATH, newline="", encoding="utf-8") as f_in, \
     open(OUT_PATH, "w", newline="", encoding="utf-8") as f_out:

    reader = csv.DictReader(f_in, delimiter=";")
    fieldnames = list(reader.fieldnames) + ["span"]
    writer = csv.DictWriter(
        f_out, fieldnames=fieldnames, delimiter=";", extrasaction="ignore"
    )
    writer.writeheader()

    for line_num, row in enumerate(reader, start=2):
        text     = row["text"]
        filename = row["filename"]
        speaker  = row["speaker"]

        try:
            content = load_file(filename)
        except FileNotFoundError:
            not_found_rows.append((line_num, filename, "FILE_NOT_FOUND", ""))
            row["span"] = "FILE_NOT_FOUND"
            writer.writerow(row)
            continue

        result, strat = find_span_with_stats(content, filename, text, speaker)
        strategy_used[strat] = strategy_used.get(strat, 0) + 1

        if result is None:
            not_found_rows.append((line_num, filename, "TEXT_NOT_FOUND", text[:70]))
            row["span"] = "TEXT_NOT_FOUND"
        else:
            row["span"] = f"{result[0]} {result[1]}"

        writer.writerow(row)

# ── Report ────────────────────────────────────────────────────────────────────
total   = sum(1 for _ in open(CSV_PATH)) - 1
matched = total - len(not_found_rows)
print(f"Processed  : {total} rows")
print(f"Matched    : {matched} ({100 * matched / total:.1f}%)")
print(f"Not found  : {len(not_found_rows)}")
print(f"\nStrategy breakdown:")
for name, count in strategy_used.items():
    print(f"  {name:<14}: {count}")
for item in not_found_rows:
    print(f"  Line {item[0]:>4}  [{item[1]}]  {item[2]}  {repr(item[3])}")
print(f"\nOutput → {OUT_PATH}")
