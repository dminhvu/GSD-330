import io
from datetime import datetime

import pandas as pd
import streamlit as st

st.set_page_config(page_title="GSD-330: BRETCON")
st.title("GSD-330: BRETCON")

st.markdown(
    """
Upload the invoice file `Open Invoices_16.9.25 (1).xlsx` (or any CSV/Excel).
This tool will:
1. Delete column A (customer name) and shift all other columns left (so original column B becomes Column A).
2. Reformat any column whose name contains 'date' to DD/MM/YYYY.
3. Convert any column whose name contains 'balance'/'amount'/'value' to numeric with 2 decimals.
4. Export as CSV.
"""
)

# Options
has_header = st.checkbox("File has header row (first row = column names)", value=True)
sheet_name = st.text_input("Excel sheet name (leave blank = first sheet)", value="")
output_filename = st.text_input("Output CSV filename", value="bre tcon_upload.csv")

uploaded_file = st.file_uploader("Choose a CSV or Excel file", type=["csv", "xlsx", "xls"])

def parse_date_value(val):
    """Try several common date formats, fallback to pandas to_datetime (dayfirst)."""
    if pd.isna(val):
        return pd.NaT
    s = str(val).strip()
    # Common formats to try
    fmts = ("%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d", "%m/%d/%Y", "%Y/%m/%d", "%d.%m.%Y")
    for fmt in fmts:
        try:
            return datetime.strptime(s, fmt).date()
        except Exception:
            continue
    # Fallback to pandas parsing (prefer day first)
    try:
        dt = pd.to_datetime(s, dayfirst=True, errors="coerce")
        if pd.isna(dt):
            return pd.NaT
        return dt.date()
    except Exception:
        return pd.NaT

def process_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    # 1. Delete column A (index 0)
    if df.shape[1] < 2:
        raise ValueError("Input must have at least 2 columns so that column A can be removed and others shift left.")
    df = df.drop(df.columns[0], axis=1).reset_index(drop=True)

    # After dropping, reset column names if there were no headers
    # If headerless, columns are 0..n-1. If header present, they retain original names (after dropping first).
    # Normalize column names to strings for safe searching
    df.columns = [str(c) for c in df.columns]

    # 2. Find probable date columns and format to DD/MM/YYYY
    date_cols = [c for c in df.columns if "date" in c.lower()]
    # If none found, try heuristics: column names containing 'doc'+'date' or 'invoice'
    if not date_cols:
        date_cols = [c for c in df.columns if any(k in c.lower() for k in ("doc", "invoice")) and "date" in c.lower()]

    # parse and format date columns
    for col in date_cols:
        parsed = df[col].apply(parse_date_value)
        # Convert to string DD/MM/YYYY, empty string if NaT
        df[col] = parsed.apply(lambda d: d.strftime("%d/%m/%Y") if pd.notna(d) else "")

    # 3. Find probable balance/amount columns and convert to numeric with 2 decimals
    balance_cols = [c for c in df.columns if any(k in c.lower() for k in ("balance", "amount", "value", "amt", "debit", "credit", "total"))]
    # If none found, try last column as balance (common pattern)
    if not balance_cols and df.shape[1] >= 1:
        balance_cols = [df.columns[-1]]

    for col in balance_cols:
        # Remove thousands separators and convert
        def to_numeric(x):
            if pd.isna(x) or str(x).strip() == "":
                return pd.NA
            s = str(x).replace(",", "").replace(" ", "")
            # handle parentheses for negative amounts (e.g., (123.45))
            if s.startswith("(") and s.endswith(")"):
                s = "-" + s[1:-1]
            try:
                return float(s)
            except Exception:
                # try pandas
                try:
                    return float(pd.to_numeric(s, errors="coerce"))
                except Exception:
                    return pd.NA

        df[col] = df[col].apply(to_numeric)
        # Round to 2 decimals
        df[col] = df[col].astype("Float64")  # nullable float
        df[col] = df[col].round(2)

    # 4. Return dataframe with shifted columns (no change to order other than deletion)
    return df

def get_csv_bytes(df: pd.DataFrame) -> bytes:
    # For numeric formatting in CSV, we'll write numbers as usual. For any Float64 columns round is already applied.
    # Use to_csv with index=False
    csv_bytes = df.to_csv(index=False, float_format="%.2f").encode("utf-8")
    return csv_bytes

if uploaded_file is not None:
    try:
        # Read file
        if uploaded_file.name.lower().endswith(".csv"):
            if has_header:
                df_in = pd.read_csv(uploaded_file, header=0)
            else:
                df_in = pd.read_csv(uploaded_file, header=None)
        else:
            # Excel
            read_kwargs = {}
            if sheet_name:
                read_kwargs["sheet_name"] = sheet_name
            else:
                read_kwargs["sheet_name"] = 0
            if has_header:
                df_in = pd.read_excel(uploaded_file, header=0, **read_kwargs)
            else:
                df_in = pd.read_excel(uploaded_file, header=None, **read_kwargs)

        if df_in.empty:
            st.error("Uploaded file is empty.")
        elif df_in.shape[1] < 2:
            st.error("Uploaded file must have at least 2 columns (so column A can be removed and others shift left).")
        else:
            st.subheader("Input preview (first 10 rows)")
            st.dataframe(df_in.head(10))

            # Process
            processed_df = process_dataframe(df_in)

            st.subheader("Processed preview (first 10 rows)")
            st.dataframe(processed_df.head(10))

            # Show which columns were treated as dates/balances
            detected_date_cols = [c for c in processed_df.columns if "date" in c.lower()]
            detected_balance_cols = [c for c in processed_df.columns if any(k in c.lower() for k in ("balance", "amount", "value", "amt", "debit", "credit", "total"))]
            st.write("Detected date columns:", detected_date_cols if detected_date_cols else "None detected")
            st.write("Detected balance/amount columns:", detected_balance_cols if detected_balance_cols else "None detected (last column used)")

            # Download button
            csv_bytes = get_csv_bytes(processed_df)
            st.download_button(
                label="Download processed CSV",
                data=csv_bytes,
                file_name=output_filename if output_filename.lower().endswith(".csv") else output_filename + ".csv",
                mime="text/csv",
            )

    except Exception as e:
        st.error(f"Error processing file: {e}")
else:
    st.info("Please upload a CSV or Excel file to begin.")
