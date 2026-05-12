import ast
import os

import pandas as pd

# ── paths ────────────────────────────────────────────────────────────────────
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

CSV_PATH = os.path.join(BASE, "data", "annotations", "fallacies", "fallacies_with_span.csv")
CSV_OUT_DIR = os.path.join(BASE, "data", "fallacies", "csv")
TXT_DIR = os.path.join(BASE, "data", "annotations", "txt")


def parse_turns(text: str):
    turns = []
    cursor = 0

    for line in text.splitlines(keepends=True):
        raw_line = line.rstrip("\n")

        # Skip empty lines
        if not raw_line.strip():
            cursor += len(line)
            continue

        start = cursor
        end = cursor + len(raw_line)

        speaker = None
        speech_text = raw_line

        # Extract speaker if present
        if ":" in raw_line:
            possible_speaker, possible_text = raw_line.split(":", 1)

            # Treat leading uppercase token as speaker
            if possible_speaker.strip():
                speaker = possible_speaker.strip()
                speech_text = possible_text.lstrip()

                # Adjust start position to exclude speaker prefix
                speech_start_offset = raw_line.index(":") + 1
                while (
                        speech_start_offset < len(raw_line)
                        and raw_line[speech_start_offset] == " "
                ):
                    speech_start_offset += 1

                start = cursor + speech_start_offset

        turns.append({
            "start": start,
            "end": end,
            "speaker": speaker,
            "text": speech_text
        })

        cursor += len(line)

    return turns


# ── main logic ───────────────────────────────────────────────────────────────
def main(csv_path: str, csv_out_dir: str) -> None:
    """Read master fallacies CSV and write one CSV per debate."""
    os.makedirs(csv_out_dir, exist_ok=True)
    df = pd.read_csv(csv_path)

    debates = sorted(df["debate_id"].unique())

    for debate in debates:
        txt_path = os.path.join(TXT_DIR, f"{debate}.txt")

        with open(txt_path, "r", encoding="utf-8") as f:
            txt = f.read()

        fallacy_tags = ["O"] * len(txt)
        components_tags = ["O"] * len(txt)

        fallacies = df[df["debate_id"] == debate]

        for _, row in fallacies.iterrows():
            spans = ast.literal_eval(str(row["text_span"]))
            start, end = spans

            for i in range(start, end):
                fallacy_tags[i] = str(row["fallacy"])
                components_tags[i] = str(row["component_type"])

        turns = parse_turns(txt)

        rows = []

        for turn_id, turn in enumerate(turns):
            start = turn["start"]
            end = turn["end"]
            speaker = turn["speaker"]

            turn_text = txt[start:end]
            turn_fallacy_labels = fallacy_tags[start:end]
            turn_components_labels = components_tags[start:end]

            rows.append({
                "id": turn_id,
                "speech_turn": turn_text,
                "fallacy_labels": turn_fallacy_labels,
                "components_labels": turn_components_labels,
                "speaker":speaker,
                "year": debate.split("_")[-1],
            })

        # Save debate CSV
        out_path = os.path.join(csv_out_dir, f"{debate}.csv")
        out_df = pd.DataFrame(rows)
        out_df.to_csv(out_path, index=False, encoding="utf-8")

        print(f"Saved: {out_path}")


if __name__ == "__main__":
    main(CSV_PATH, CSV_OUT_DIR)
