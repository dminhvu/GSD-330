import io
from datetime import datetime

import pandas as pd
import streamlit as st

st.set_page_config(page_title="GSD-330: BRETCON")
st.title("GSD-330: BRETCON")

st.markdown(
    """
Upload the invoice file `Open Invoices_16.9.25 (1).xlsx` (or any CSV/Excel).
Behavior (fixed):
- single-sheet Excel only (first sheet used)
- first row is always header
- remove column A (customer name) and shift everything left
- auto-detect & reformat date columns to DD/MM/YYYY
- auto-detect & convert balance/amount columns to numeric with 2 decimals
- download output as bretcon_upload.csv
"""
)

OUTPUT_FILENAME = "bretcon_upload.csv"


def parse_date_value(val):
    if pd.isna(val):
        return pd.NaT
    s = str(val).strip()
    fmts = ("%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d", "%m/%d/%Y", "%Y/%m/%d", "%d.%m.%Y")
    for fmt in fmts:
        try:
            return datetime.strptime(s, fmt).date()
        except Exception:
            continue
    try:
        dt = pd.to_datetime(s, dayfirst=True, errors="coerce")
        if pd.isna(dt):
            return pd.NaT
        return dt.date()
    except Exception:
        return pd.NaT


def to_numeric_value(x):
    if pd.isna(x) or str(x).strip() == "":
        return pd.NA
    s = str(x).replace(",", "").replace(" ", "")
    if s.startswith("(") and s.endswith(")"):
        s = "-" + s[1:-1]
    try:
        return float(s)
    except Exception:
        try:
            return float(pd.to_numeric(s, errors="coerce"))
        except Exception:
            return pd.NA


def process_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    # Require at least 2 columns so we can drop the first
    if df.shape[1] < 2:
        raise ValueError("Input must have at least 2 columns (so column A can be removed).")

    # 1) Delete column A (customer name) and shift all others left
    df = df.drop(df.columns[0], axis=1).reset_index(drop=True)

    # Normalize column names to strings
    df.columns = [str(c) for c in df.columns]

    # 2) Detect date columns (header contains 'date' case-insensitive)
    date_cols = [c for c in df.columns if "date" in c.lower()]
    # Fallback heuristics: 'document', 'doc', 'invoice' with 'date' nearby (already covered), or common names
    if not date_cols:
        heuristics = ["documentdate", "docdate", "invoice date", "invoice_date", "document date"]
        for c in df.columns:
            low = c.lower().replace(" ", "")
            if any(h in low for h in heuristics):
                date_cols.append(c)
    # Parse & format date columns
    for col in date_cols:
        parsed = df[col].apply(parse_date_value)
        df[col] = parsed.apply(lambda d: d.strftime("%d/%m/%Y") if pd.notna(d) else "")

    # 3) Detect balance/amount columns
    balance_keywords = ("balance", "amount", "value", "amt", "debit", "credit", "total", "open")
    balance_cols = [c for c in df.columns if any(k in c.lower() for k in balance_keywords)]
    # Fallback: if none detected, use last column as balance
    if not balance_cols:
        balance_cols = [df.columns[-1]]

    for col in balance_cols:
        df[col] = df[col].apply(to_numeric_value)
        # Use pandas nullable float and round to 2 decimals
        df[col] = df[col].astype("Float64")
        df[col] = df[col].round(2)

    return df


def get_csv_bytes(df: pd.DataFrame) -> bytes:
    # Ensure numeric formatting to 2 decimals in CSV
    return df.to_csv(index=False, float_format="%.2f").encode("utf-8")


st.write("Upload your Excel or CSV file (first row must be header):")
uploaded_file = st.file_uploader("Choose a file", type=["csv", "xlsx", "xls"])

if uploaded_file is not None:
    try:
        # Read (header always present, single sheet)
        if uploaded_file.name.lower().endswith(".csv"):
            df_in = pd.read_csv(uploaded_file, header=0)
        else:
            df_in = pd.read_excel(uploaded_file, header=0, sheet_name=0)

        if df_in.empty:
            st.error("Uploaded file is empty.")
        elif df_in.shape[1] < 2:
            st.error("Uploaded file must have at least 2 columns so column A can be removed.")
        else:
            st.subheader("Input preview (first 8 rows)")
            st.dataframe(df_in.head(8))

            processed_df = process_dataframe(df_in)

            st.subheader("Processed preview (first 8 rows)")
            st.dataframe(processed_df.head(8))

            # Info about detected columns
            detected_date_cols = [c for c in processed_df.columns if "date" in c.lower()]
            detected_balance_cols = [
                c
                for c in processed_df.columns
                if any(k in c.lower() for k in ("balance", "amount", "value", "amt", "debit", "credit", "total", "open"))
            ]
            if not detected_date_cols:
                st.info("No column header containing 'date' detected — no date formatting was applied.")
            else:
                st.write("Date columns formatted to DD/MM/YYYY:", detected_date_cols)
            st.write("Balance/amount columns converted to numeric (2 decimals):", detected_balance_cols or [processed_df.columns[-1]])

            csv_bytes = get_csv_bytes(processed_df)
            st.download_button(
                label="Download processed CSV",
                data=csv_bytes,
                file_name=OUTPUT_FILENAME,
                mime="text/csv",
            )

    except Exception as e:
        st.error(f"Error processing file: {e}")
else:
    st.info("Please upload a CSV or Excel file to begin.")
