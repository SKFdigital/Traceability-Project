from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from database import get_db
from settings import settings

import pandas as pd
import requests
import io
import re
import math

from datetime import datetime, timedelta

router = APIRouter()

# =========================================================
# CACHE
# =========================================================

MASTER_CACHE = []
FLOW_CACHE = {}

LAST_REFRESH = None

CACHE_DURATION_MINUTES = 5

# =========================================================
# SHEETS
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


def extract_bearing_family(text):

    if not text:
        return ""

    text = str(text).upper()

    text = text.replace(" ", "")

    text = re.sub(r'IM|OM', '', text)

    match = re.search(r'([0-9]{4,})', text)

    if match:
        return match.group(1)

    return text[:4]


def extract_mo_prefix(text):

    if not text:
        return ""

    text = str(text).upper().replace(" ", "")

    return text[:4]


def download_excel(url):

    response = requests.get(url)

    if response.status_code != 200:
        raise Exception(f"Failed downloading excel")

    return io.BytesIO(response.content)


def load_excel_sheets(url):

    excel_data = download_excel(url)

    xls = pd.ExcelFile(excel_data)

    sheets = {}

    for sheet in xls.sheet_names:

        try:

            df = pd.read_excel(xls, sheet_name=sheet)

            df.columns = [str(c).strip() for c in df.columns]

            sheets[sheet] = df

        except Exception as e:

            print("FAILED SHEET:", sheet, str(e))

    return sheets


# =========================================================
# CACHE REFRESH
# =========================================================

def refresh_cache():

    global MASTER_CACHE
    global FLOW_CACHE
    global LAST_REFRESH

    print("REFRESHING TRACEABILITY CACHE")

    MASTER_CACHE = []
    FLOW_CACHE = {}

    # -----------------------------------------------------
    # LOAD FILES
    # -----------------------------------------------------

    jobwork_sheets = load_excel_sheets(
        settings.JOBWORK_REPORT_URL
    )

    trb_sheets = load_excel_sheets(
        settings.TRB_MASTER_URL
    )

    dgbb_sheets = load_excel_sheets(
        settings.DGBB_MASTER_URL
    )

    trace_sheets = load_excel_sheets(
        settings.TRACEABILITY_MASTER_URL
    )

    # =====================================================
    # MASTER OBJECT
    # =====================================================

    mo_map = {}

    # =====================================================
    # JOBWORK
    # =====================================================

    for sheet_name, df in jobwork_sheets.items():

        if "PO / PR No." not in df.columns:
            continue

        for _, row in df.iterrows():

            mo = normalize_text(
                row.get("PO / PR No.")
            )

            family = extract_bearing_family(mo)

            if family not in mo_map:

                mo_map[family] = {
                    "mo": mo,
                    "family": family,
                    "start_date": None,
                    "end_date": None,
                    "sho_qty": 0,
                    "transit_qty": 0,
                    "channel_qty": 0,
                    "output_qty": 0,
                    "status": "Running",
                    "channel": "",
                    "stages": []
                }

            date = parse_date_safe(
                row.get("JW Challan Date")
            )

            close_date = parse_date_safe(
                row.get("Last Challan Date")
            )

            qty_approved = clean_nan(
                row.get("Qty Approved")
            ) or 0

            qty_returned = clean_nan(
                row.get("Qty Returned")
            ) or 0

            ring_name = normalize_text(
                row.get("Product")
            )

            # SHO
            mo_map[family]["stages"].append({

                "stage": "SHO",

                "date": str(date) if date else "",

                "department": "SHO",

                "ring_name": ring_name,

                "channel": "",

                "production": qty_approved,

                "cumulative_production": "",

                "quantity": qty_approved,

                "returned_qty": "",

                "output_quantity": "",

                "towards_packaging": "",

                "end_buffer": "",

                "next_station": "Transit Buffer",

                "status": normalize_text(
                    row.get("Current Status")
                ),

                "remark": normalize_text(
                    row.get("Challan Type(Indirect & Direct Material)")
                )
            })

            # TRANSIT
            mo_map[family]["stages"].append({

                "stage": "Transit Buffer",

                "date": str(close_date) if close_date else "",

                "department": "Transit Buffer",

                "ring_name": ring_name,

                "channel": "",

                "production": qty_returned,

                "cumulative_production": "",

                "quantity": "",

                "returned_qty": qty_returned,

                "output_quantity": "",

                "towards_packaging": "",

                "end_buffer": "",

                "next_station": "Channel",

                "status": "Returned",

                "remark": ""
            })

            mo_map[family]["sho_qty"] += qty_approved

            mo_map[family]["transit_qty"] += qty_returned

            if not mo_map[family]["start_date"]:
                mo_map[family]["start_date"] = str(date)

    # =====================================================
    # TRB
    # =====================================================

    for sheet_name, df in trb_sheets.items():

        if sheet_name not in TRB_LINE_SHEETS:
            continue

        if "MO" not in df.columns:
            continue

        for _, row in df.iterrows():

            mo = normalize_text(
                row.get("MO")
            )

            family = extract_bearing_family(mo)

            if family not in mo_map:
                continue

            production = clean_nan(
                row.get("Production")
            ) or 0

            cumulative = clean_nan(
                row.get("Cumulative production")
            ) or 0

            mo_map[family]["channel"] = "TRB"

            mo_map[family]["channel_qty"] += production

            mo_map[family]["stages"].append({

                "stage": "TRB",

                "date": str(
                    parse_date_safe(row.get("Date"))
                ),

                "department": "TRB",

                "ring_name": mo,

                "channel": sheet_name,

                "shift": clean_nan(
                    row.get("Shift")
                ),

                "production": production,

                "cumulative_production": cumulative,

                "quantity": "",

                "returned_qty": "",

                "output_quantity": "",

                "towards_packaging": clean_nan(
                    row.get("Towards Packaging")
                ),

                "end_buffer": clean_nan(
                    row.get("END Buffer")
                ),

                "next_station": normalize_text(
                    row.get("Next_Station")
                ),

                "status": normalize_text(
                    row.get("Remark")
                ),

                "remark": normalize_text(
                    row.get("Remark")
                )
            })

    # =====================================================
    # DGBB
    # =====================================================

    for sheet_name, df in dgbb_sheets.items():

        if sheet_name not in DGBB_LINE_SHEETS:
            continue

        if "MO" not in df.columns:
            continue

        for _, row in df.iterrows():

            mo = normalize_text(
                row.get("MO")
            )

            prefix = extract_mo_prefix(mo)

            matched_family = None

            for family, obj in mo_map.items():

                original_mo = extract_mo_prefix(
                    obj["mo"]
                )

                if original_mo == prefix:
                    matched_family = family
                    break

            if not matched_family:
                continue

            production = clean_nan(
                row.get("Production")
            ) or 0

            cumulative = clean_nan(
                row.get("Cumulative production")
            ) or 0

            mo_map[matched_family]["channel"] = "DGBB"

            mo_map[matched_family]["channel_qty"] += production

            mo_map[matched_family]["stages"].append({

                "stage": "DGBB",

                "date": str(
                    parse_date_safe(row.get("Date"))
                ),

                "department": "DGBB",

                "ring_name": mo,

                "channel": sheet_name,

                "shift": clean_nan(
                    row.get("Shift")
                ),

                "production": production,

                "cumulative_production": cumulative,

                "quantity": "",

                "returned_qty": "",

                "output_quantity": "",

                "towards_packaging": clean_nan(
                    row.get("Towards Packaging")
                ),

                "end_buffer": clean_nan(
                    row.get("END Buffer")
                ),

                "next_station": normalize_text(
                    row.get("Next_Station")
                ),

                "status": normalize_text(
                    row.get("Remark")
                ),

                "remark": normalize_text(
                    row.get("Remark")
                )
            })

    # =====================================================
    # TRACEABILITY OUTPUT
    # =====================================================

    for sheet_name, df in trace_sheets.items():

        if sheet_name not in TRACEABILITY_SHEETS:
            continue

        if "MO" not in df.columns:
            continue

        for _, row in df.iterrows():

            mo = normalize_text(
                row.get("MO")
            )

            family = extract_bearing_family(mo)

            if family not in mo_map:
                continue

            production = clean_nan(
                row.get("Production")
            ) or 0

            mo_map[family]["output_qty"] += production

            end_date = parse_date_safe(
                row.get("Date")
            )

            mo_map[family]["end_date"] = str(end_date)

            mo_map[family]["stages"].append({

                "stage": "Channel Output",

                "date": str(end_date),

                "department": "Packaging",

                "ring_name": mo,

                "channel": normalize_text(
                    row.get("Source Channel")
                ),

                "shift": clean_nan(
                    row.get("Shift")
                ),

                "production": production,

                "cumulative_production": clean_nan(
                    row.get("Cumulative production")
                ),

                "quantity": "",

                "returned_qty": "",

                "output_quantity": production,

                "towards_packaging": "",

                "end_buffer": "",

                "next_station": "FG Store",

                "status": normalize_text(
                    row.get("Remark")
                ),

                "remark": normalize_text(
                    row.get("Remark")
                )
            })

    # =====================================================
    # FINALIZE
    # =====================================================

    for family, obj in mo_map.items():

        obj["total_stages"] = len(
            obj["stages"]
        )

        obj["latest_activity"] = (
            obj["end_date"]
            or obj["start_date"]
        )

        obj["stages"].sort(
            key=lambda x: x.get("date") or ""
        )

        MASTER_CACHE.append({

            "mo": obj["mo"],

            "family": obj["family"],

            "start_date": obj["start_date"],

            "end_date": obj["end_date"],

            "sho_qty": obj["sho_qty"],

            "transit_qty": obj["transit_qty"],

            "channel": obj["channel"],

            "channel_qty": obj["channel_qty"],

            "output_qty": obj["output_qty"],

            "status": obj["status"],

            "total_stages": obj["total_stages"],

            "latest_activity": obj["latest_activity"]
        })

        FLOW_CACHE[obj["mo"]] = obj

    LAST_REFRESH = datetime.now()

    print("CACHE REFRESH DONE")


# =========================================================
# ENSURE CACHE
# =========================================================

def ensure_cache():

    global LAST_REFRESH

    if LAST_REFRESH is None:
        refresh_cache()
        return

    diff = datetime.now() - LAST_REFRESH

    if diff > timedelta(
        minutes=CACHE_DURATION_MINUTES
    ):
        refresh_cache()


# =========================================================
# MASTER API
# =========================================================

@router.get("/traceability_all_mos")
def get_all_mos():

    try:

        ensure_cache()

        return {
            "status": "success",
            "count": len(MASTER_CACHE),
            "data": MASTER_CACHE
        }

    except Exception as e:

        raise HTTPException(
            status_code=500,
            detail=str(e)
        )


# =========================================================
# FLOW API
# =========================================================

@router.get("/traceability_report/{mo}")
def get_flow(mo: str):

    try:

        ensure_cache()

        if mo not in FLOW_CACHE:

            raise HTTPException(
                status_code=404,
                detail="MO not found"
            )

        return {
            "status": "success",
            "data": [
                FLOW_CACHE[mo]
            ]
        }

    except Exception as e:

        raise HTTPException(
            status_code=500,
            detail=str(e)
        )
