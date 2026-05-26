```python
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from database import get_db
from settings import settings

import pandas as pd
import requests
import io
import re
import math

from datetime import datetime

router = APIRouter()

# =========================================================
# CONFIG
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


def clean_nan(value):

    try:

        if pd.isna(value):
            return None

    except:
        pass

    return value


def extract_base_mo(mo):

    if not mo:
        return ""

    mo = str(mo).upper().strip()

    mo = mo.replace(" ", "")

    mo = re.sub(r'IM|OM', '', mo)

    match = re.search(r'(M0[A-Z0-9]+)', mo)

    if not match:
        return mo

    base = match.group(1)

    base = re.split(r'[-/]', base)[0]

    return base


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

    if not date1 or not date2:
        return False

    try:

        diff = abs((date1 - date2).days)

        return diff <= days

    except:
        return False


def download_excel(url):

    response = requests.get(url)

    if response.status_code != 200:
        raise Exception(f"Failed to download Excel: {url}")

    return io.BytesIO(response.content)


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

            print(f"Failed Sheet {sheet}: {e}")

    return sheets

# =========================================================
# ALL MO MASTER
# =========================================================

@router.get("/traceability_all_mos")
def get_all_traceability_mos():

    try:

        final_records = {}

        # =================================================
        # JOBWORK
        # =================================================

        jobwork_sheets = load_excel_sheets(
            settings.JOBWORK_REPORT_URL
        )

        for sheet_name, df in jobwork_sheets.items():

            if "PO / PR No." not in df.columns:
                continue

            for _, row in df.iterrows():

                raw_mo = normalize_text(
                    row.get("PO / PR No.")
                )

                normalized = extract_base_mo(raw_mo)

                if not normalized:
                    continue

                if normalized not in final_records:

                    final_records[normalized] = {
                        "mo": normalized,
                        "stages": [],
                        "total_output": 0,
                        "latest_date": None
                    }

                final_records[normalized]["stages"].append({
                    "stage": "SHO",
                    "department": "SHO",
                    "in_date": parse_date_safe(
                        row.get("JW Challan Date")
                    ),
                    "out_date": parse_date_safe(
                        row.get("Last Challan Date")
                    ),
                    "quantity": clean_nan(
                        row.get("Qty Approved")
                    ),
                    "returned_qty": clean_nan(
                        row.get("Qty Returned")
                    ),
                    "status": normalize_text(
                        row.get("Current Status")
                    )
                })

        # =================================================
        # TRB
        # =================================================

        trb_sheets = load_excel_sheets(
            settings.TRB_MASTER_URL
        )

        for sheet_name, df in trb_sheets.items():

            if sheet_name not in TRB_LINE_SHEETS:
                continue

            if "MOType" not in df.columns:
                continue

            for _, row in df.iterrows():

                raw_mo = normalize_text(
                    row.get("MOType")
                )

                normalized = extract_base_mo(raw_mo)

                if not normalized:
                    continue

                if normalized not in final_records:

                    final_records[normalized] = {
                        "mo": normalized,
                        "stages": [],
                        "total_output": 0,
                        "latest_date": None
                    }

                production = clean_nan(
                    row.get("Production")
                )

                cumulative = clean_nan(
                    row.get("Cumulative production")
                )

                final_records[normalized]["stages"].append({

                    "stage": "TRB",

                    "department": sheet_name,

                    "channel": sheet_name,

                    "date": parse_date_safe(
                        row.get("Date")
                    ),

                    "shift": clean_nan(
                        row.get("Shift")
                    ),

                    "production": production,

                    "cumulative_production": cumulative,

                    "towards_packaging": clean_nan(
                        row.get("Towards Packaging")
                    ),

                    "end_buffer": clean_nan(
                        row.get("END Buffer")
                    ),

                    "next_station": normalize_text(
                        row.get("Next_Station")
                    ),

                    "remark": normalize_text(
                        row.get("Remark")
                    ),

                    "tag_type": normalize_text(
                        row.get("Tag Type")
                    ),

                    "packaging_details": normalize_text(
                        row.get("Packaging Details")
                    )
                })

        # =================================================
        # DGBB
        # =================================================

        dgbb_sheets = load_excel_sheets(
            settings.DGBB_MASTER_URL
        )

        for sheet_name, df in dgbb_sheets.items():

            if sheet_name not in DGBB_LINE_SHEETS:
                continue

            if "MOType" not in df.columns:
                continue

            for _, row in df.iterrows():

                raw_mo = normalize_text(
                    row.get("MOType")
                )

                normalized = extract_base_mo(raw_mo)

                if not normalized:
                    continue

                if normalized not in final_records:

                    final_records[normalized] = {
                        "mo": normalized,
                        "stages": [],
                        "total_output": 0,
                        "latest_date": None
                    }

                final_records[normalized]["stages"].append({

                    "stage": "DGBB",

                    "department": sheet_name,

                    "channel": sheet_name,

                    "date": parse_date_safe(
                        row.get("Date")
                    ),

                    "shift": clean_nan(
                        row.get("Shift")
                    ),

                    "production": clean_nan(
                        row.get("Production")
                    ),

                    "cumulative_production": clean_nan(
                        row.get("Cumulative production")
                    ),

                    "towards_packaging": clean_nan(
                        row.get("Towards Packaging")
                    ),

                    "next_station": normalize_text(
                        row.get("Next_Station")
                    ),

                    "remark": normalize_text(
                        row.get("Remark")
                    )
                })

        # =================================================
        # TRACEABILITY
        # =================================================

        trace_sheets = load_excel_sheets(
            settings.TRACEABILITY_MASTER_URL
        )

        for sheet_name, df in trace_sheets.items():

            if sheet_name not in TRACEABILITY_SHEETS:
                continue

            if "MOType" not in df.columns:
                continue

            for _, row in df.iterrows():

                raw_mo = normalize_text(
                    row.get("MOType")
                )

                normalized = extract_base_mo(raw_mo)

                if not normalized:
                    continue

                if normalized not in final_records:

                    final_records[normalized] = {
                        "mo": normalized,
                        "stages": [],
                        "total_output": 0,
                        "latest_date": None
                    }

                production = clean_nan(
                    row.get("Production")
                )

                final_records[normalized]["stages"].append({

                    "stage": "CHANNEL OUT",

                    "department": "PACKAGING",

                    "channel": normalize_text(
                        row.get("Source Channel")
                    ),

                    "date": parse_date_safe(
                        row.get("Date")
                    ),

                    "shift": clean_nan(
                        row.get("Shift")
                    ),

                    "output_quantity": production,

                    "remark": normalize_text(
                        row.get("Remark")
                    )
                })

                if production:

                    current = final_records[
                        normalized
                    ]["total_output"]

                    final_records[
                        normalized
                    ]["total_output"] = current + production

        # =================================================
        # FINAL SUMMARY
        # =================================================

        response = []

        for mo, details in final_records.items():

            stages = details["stages"]

            latest_date = None

            for s in stages:

                d = s.get("date")

                if d:

                    if not latest_date or d > latest_date:
                        latest_date = d

            response.append({

                "mo": mo,

                "total_stages": len(stages),

                "latest_activity": latest_date,

                "total_output": details["total_output"],

                "stages": stages
            })

        response.sort(
            key=lambda x: x.get("latest_activity")
            or datetime.min.date(),
            reverse=True
        )

        return {
            "status": "success",
            "count": len(response),
            "data": response
        }

    except Exception as e:

        raise HTTPException(
            status_code=500,
            detail=str(e)
        )

# =========================================================
# SINGLE MO DETAIL
# =========================================================

@router.get("/traceability_report/{mo_number}")
def get_traceability_history(
    mo_number: str,
    db: Session = Depends(get_db)
):

    all_data = get_all_traceability_mos()

    target = extract_base_mo(mo_number)

    filtered = []

    for row in all_data["data"]:

        if row["mo"] == target:

            filtered.append(row)

    return {
        "status": "success",
        "searched_mo": mo_number,
        "normalized_mo": target,
        "data": filtered
    }
```
