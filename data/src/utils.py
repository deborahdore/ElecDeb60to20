import re

import pandas as pd
import rootutils

rootutils.setup_root(__file__, indicator=".project-root", pythonpath=True, cwd=True)


def clean_debates(full_debates_file: str = "data/full_debates.csv"):
    df = pd.read_csv(full_debates_file)
    df_valid = df[~pd.isna(df["speaker"])].copy()
    df_nan = df[pd.isna(df["speaker"])]

    fixed_rows = []

    for idx, row in df_nan.iterrows():
        date = row.date
        text = row.concatenated_speech

        pattern = r"([A-Z][A-Z\.,\s'-]*:)(.*?)(?=[A-Z][A-Z\.,\s'-]*:|$)"
        matches = re.finditer(pattern, text, flags=re.DOTALL)

        # Split on speaker labels
        for m in matches:
            speaker = m.group(1).strip()
            speech = m.group(2).strip()
            fixed_rows.append({
                "date": date,
                "speaker": speaker,
                "concatenated_speech": speech
            })

    df_clean = pd.concat([df_valid, pd.DataFrame(fixed_rows)], axis=0, ignore_index=True)
    df_clean = df_clean.dropna().reset_index(drop=True)

    df_clean.to_csv(full_debates_file, index=False)
