from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from database import get_db
from settings import settings

import pandas as pd
import requests
import io
import re

from datetime import datetime, timedelta

router = APIRouter()

# =========================================================
# SHEET CONFIGURATION
# =========================================================

TRB_LINE_SHEETS = ["T3", "T4", "T5", "T6"]

DGBB_LINE_SHEETS = [
    "CH02",
    "CH03",
    "CH04",
    "CH05",
    "CH08",
    "CH12",
    "CH13"
]

TRACEABILITY_SHEETS = [
    "Channel Data Master"
]

# =========================================================
# HELPERS
# =========================================================

def normalize_text(value):
    if pd.isna(value):
        return ""
    return str(value).strip()

def extract_base_mo(mo):
    """
    Intelligent MO normalization.

    Handles:
    - IM / OM removal
    - bearing variants
    - grease variants
    - sealing variants
    """

    if not mo:
        return ""

    mo = str(mo).upper().strip()

    # remove spaces
    mo = mo.replace(" ", "")

    # remove IM / OM
    mo = re.sub(r'IM|OM', '', mo)

    # keep first major bearing family
    match = re.search(r'([A-Z0-9]+[0-9]{3,})', mo)

    if match:
        base = match.group(1)

        # trim after variant symbols
        base = re.split(r'[-/]', base)[0]

        return base

    return mo

def parse_date_safe(value):

    try:

        if pd.isna(value):
            return None

        parsed = pd.to_datetime(value, errors='coerce')

        if pd.isna(parsed):
            return None

        return parsed.date()

    except:
        return None


def within_date_window(date1, date2, days=30):

    if date1 is None or date2 is None:
        return False

    try:

        if pd.isna(date1) or pd.isna(date2):
            return False

        if isinstance(date1, pd.Timestamp):
            date1 = date1.date()

        if isinstance(date2, pd.Timestamp):
            date2 = date2.date()

        diff = abs((date1 - date2).days)

        return diff <= days

    except:
        return False


def download_excel(url):
    response = requests.get(url)

    if response.status_code != 200:
        raise Exception(f"Failed to download Excel: {url}")

    return io.BytesIO(response.content)

# =========================================================
# LOAD EXCEL FILES
# =========================================================

def load_excel_sheets(url):
    excel_data = download_excel(url)

    xls = pd.ExcelFile(excel_data)

    sheets = {}

    for sheet in xls.sheet_names:
        try:
            df = pd.read_excel(xls, sheet_name=sheet)

            df.columns = [str(col).strip() for col in df.columns]

            sheets[sheet] = df

        except Exception as e:
            print(f"Failed sheet {sheet}: {e}")

    return sheets

# =========================================================
# JOBWORK PARSER
# =========================================================

def parse_jobwork_data(sheets, target_mo):

    matched = []

    for sheet_name, df in sheets.items():

        if "PO / PR No." not in df.columns:
            continue

        for _, row in df.iterrows():

            mo = normalize_text(row.get("PO / PR No."))

            normalized = extract_base_mo(mo)

            if normalized != target_mo:
                continue

            matched.append({
                "source": "JOBWORK",
                "sheet": sheet_name,
                "date": parse_date_safe(row.get("JW Challan Date")),
                "close_date": parse_date_safe(row.get("Last Challan Date")),
                "mo": mo,
                "normalized_mo": normalized,
                "challan_no": normalize_text(row.get("JW Challan No.")),
                "job_worker": normalize_text(row.get("Job Worker (JW)")),
                "qty_approved": row.get("Qty Approved"),
                "qty_returned": row.get("Qty Returned"),
                "status": normalize_text(row.get("Current Status")),
                "department": normalize_text(row.get("Department")),
            })

    return matched

# =========================================================
# TRB PARSER
# =========================================================

def parse_trb_data(sheets, target_mo, reference_dates):

    matched = []

    for sheet_name, df in sheets.items():

        if sheet_name not in TRB_LINE_SHEETS:
            continue

        if "MO" not in df.columns:
            continue

        for _, row in df.iterrows():

            mo = normalize_text(row.get("MO"))

            normalized = extract_base_mo(mo)

            if target_mo not in normalized and normalized not in target_mo:
                continue

            row_date = parse_date_safe(row.get("Date"))

            valid_date = False

            for ref_date in reference_dates:
                if within_date_window(ref_date, row_date):
                    valid_date = True
                    break

            if not valid_date and reference_dates:
                continue

            matched.append({
                "source": "TRB",
                "sheet": sheet_name,
                "channel": sheet_name,
                "date": row_date,
                "shift": row.get("Shift"),
                "mo": mo,
                "normalized_mo": normalized,
                "production": row.get("Production"),
                "cumulative_production": row.get("Cumulative production"),
                "towards_packaging": row.get("Towards Packaging"),
                "next_station": row.get("Next_Station"),
                "remark": normalize_text(row.get("Remark")),
            })

    return matched

# =========================================================
# DGBB PARSER
# =========================================================

def parse_dgbb_data(sheets, target_mo, reference_dates):

    matched = []

    target_prefix = target_mo[:4]

    for sheet_name, df in sheets.items():

        if sheet_name not in DGBB_LINE_SHEETS:
            continue

        if "MO" not in df.columns:
            continue

        for _, row in df.iterrows():

            mo = normalize_text(row.get("MO"))

            normalized = extract_base_mo(mo)

            if not normalized.startswith(target_prefix):
                continue

            row_date = parse_date_safe(row.get("Date"))

            valid_date = False

            for ref_date in reference_dates:
                if within_date_window(ref_date, row_date):
                    valid_date = True
                    break

            if not valid_date and reference_dates:
                continue

            matched.append({
                "source": "DGBB",
                "sheet": sheet_name,
                "channel": sheet_name,
                "date": row_date,
                "shift": row.get("Shift"),
                "mo": mo,
                "normalized_mo": normalized,
                "production": row.get("Production"),
                "cumulative_production": row.get("Cumulative production"),
                "towards_packaging": row.get("Towards Packaging"),
                "next_station": row.get("Next_Station"),
                "remark": normalize_text(row.get("Remark")),
            })

    return matched

# =========================================================
# TRACEABILITY PARSER
# =========================================================

def parse_traceability_data(sheets, target_mo):

    matched = []

    for sheet_name, df in sheets.items():

        if sheet_name not in TRACEABILITY_SHEETS:
            continue

        if "MO" not in df.columns:
            continue

        for _, row in df.iterrows():

            mo = normalize_text(row.get("MO"))

            normalized = extract_base_mo(mo)

            if target_mo not in normalized and normalized not in target_mo:
                continue

            matched.append({
                "source": "TRACEABILITY",
                "sheet": sheet_name,
                "date": parse_date_safe(row.get("Date")),
                "source_channel": normalize_text(row.get("Source Channel")),
                "production": row.get("Production"),
                "next_station": row.get("Next_Station"),
                "remark": normalize_text(row.get("Remark")),
            })

    return matched

# =========================================================
# MAIN TRACEABILITY ROUTE
# =========================================================
@router.get("/traceability_report/{mo_number}")
def get_traceability_history(mo_number: str, db: Session = Depends(get_db)):

    try:

        print("TRACEABILITY API CALLED")
        print("INPUT MO:", mo_number)

        normalized_target = extract_base_mo(mo_number)

        print("NORMALIZED MO:", normalized_target)

        # -------------------------------------------------
        # LOAD FILES
        # -------------------------------------------------

        print("LOADING JOBWORK")
        jobwork_sheets = load_excel_sheets(settings.JOBWORK_REPORT_URL)

        print("LOADING TRB")
        trb_sheets = load_excel_sheets(settings.TRB_MASTER_URL)

        print("LOADING DGBB")
        dgbb_sheets = load_excel_sheets(settings.DGBB_MASTER_URL)

        print("LOADING TRACEABILITY")
        trace_sheets = load_excel_sheets(settings.TRACEABILITY_MASTER_URL)

        print("FILES LOADED SUCCESSFULLY")

        # -------------------------------------------------
        # JOBWORK
        # -------------------------------------------------

        print("PARSING JOBWORK")

        jobwork_data = parse_jobwork_data(
            jobwork_sheets,
            normalized_target
        )

        print("JOBWORK RECORDS:", len(jobwork_data))

        reference_dates = []

        for row in jobwork_data:
            if row["date"]:
                reference_dates.append(row["date"])

        # -------------------------------------------------
        # TRB
        # -------------------------------------------------

        print("PARSING TRB")

        trb_data = parse_trb_data(
            trb_sheets,
            normalized_target,
            reference_dates
        )

        print("TRB RECORDS:", len(trb_data))

        # -------------------------------------------------
        # DGBB
        # -------------------------------------------------

        print("PARSING DGBB")

        dgbb_data = parse_dgbb_data(
            dgbb_sheets,
            normalized_target,
            reference_dates
        )

        print("DGBB RECORDS:", len(dgbb_data))

        # -------------------------------------------------
        # TRACEABILITY
        # -------------------------------------------------

        print("PARSING TRACEABILITY")

        traceability_data = parse_traceability_data(
            trace_sheets,
            normalized_target
        )

        print("TRACEABILITY RECORDS:", len(traceability_data))

        # -------------------------------------------------
        # FINAL TIMELINE
        # -------------------------------------------------

        timeline = (
            jobwork_data +
            trb_data +
            dgbb_data +
            traceability_data
        )

        timeline.sort(
            key=lambda x: x.get("date") or datetime.min.date()
        )

        print("FINAL TIMELINE:", len(timeline))

        return {
            "status": "success",
            "searched_mo": mo_number,
            "normalized_mo": normalized_target,
            "total_records": len(timeline),
            "timeline": timeline
        }

    except Exception as e:

        import traceback

        print("============== TRACEABILITY ERROR ==============")
        print(str(e))
        print(traceback.format_exc())
        print("===============================================")

        raise HTTPException(
            status_code=500,
            detail=str(e)
        )

