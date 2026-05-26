from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from database import get_db
from settings import settings

import pandas as pd
import requests
import io
import re
import math

from collections import defaultdict
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

    try:

        if pd.isna(value):
            return ""

    except:
        pass

    return str(value).strip()


def clean_nan(value):

    if value is None:
        return None

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

        parsed = pd.to_datetime(
            value,
            errors='coerce',
            dayfirst=True
        )

        if pd.isna(parsed):
            return None

        return parsed.date()

    except:
        return None


def extract_base_mo(mo):

    if not mo:
        return ""

    mo = str(mo).upper().strip()

    mo = mo.replace(" ", "")

    mo = re.sub(r'IM|OM', '', mo)

    match = re.search(r'([A-Z0-9]+)', mo)

    if not match:
        return mo

    base = match.group(1)

    base = re.split(r'[-/]', base)[0]

    return base


def get_dgbb_prefix(mo):

    mo = extract_base_mo(mo)

    return mo[:4]


def within_date_window(date1, date2, days=45):

    if not date1 or not date2:
        return False

    try:

        if isinstance(date1, pd.Timestamp):
            date1 = date1.date()

        if isinstance(date2, pd.Timestamp):
            date2 = date2.date()

        return abs((date1 - date2).days) <= days

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

            print(f"FAILED SHEET {sheet}: {e}")

    return sheets

# =========================================================
# JOBWORK PARSER
# =========================================================

def parse_jobwork_data(sheets):

    records = []

    for sheet_name, df in sheets.items():

        if "PO / PR No." not in df.columns:
            continue

        for _, row in df.iterrows():

            mo = normalize_text(row.get("PO / PR No."))

            if not mo:
                continue

            normalized = extract_base_mo(mo)

            records.append({

                "source": "JOBWORK",
                "sheet": sheet_name,
                "department": "SHO",

                "date": parse_date_safe(
                    row.get("JW Challan Date")
                ),

                "close_date": parse_date_safe(
                    row.get("Last Challan Date")
                ),

                "mo": mo,
                "normalized_mo": normalized,

                "challan_no": normalize_text(
                    row.get("JW Challan No.")
                ),

                "job_worker": normalize_text(
                    row.get("Job Worker (JW)")
                ),

                "ring_type": normalize_text(
                    row.get("Challan Type(Indirect & Direct Material)")
                ),

                "product": normalize_text(
                    row.get("Product")
                ),

                "qty_sent": clean_nan(
                    row.get("Qty Sent")
                ),

                "qty_approved": clean_nan(
                    row.get("Qty Approved")
                ),

                "qty_returned": clean_nan(
                    row.get("Qty Returned")
                ),

                "difference_balance_qty": clean_nan(
                    row.get("Difference Balance Qty")
                ),

                "status": normalize_text(
                    row.get("Current Status")
                ),
            })

    return records

# =========================================================
# TRB PARSER
# =========================================================

def parse_trb_data(sheets):

    records = []

    for sheet_name, df in sheets.items():

        if sheet_name not in TRB_LINE_SHEETS:
            continue

        if "MO" not in df.columns:
            continue

        for _, row in df.iterrows():

            mo = normalize_text(row.get("MO"))

            if not mo:
                continue

            normalized = extract_base_mo(mo)

            records.append({

                "source": "TRB",
                "sheet": sheet_name,
                "department": "CHANNEL",
                "channel": "TRB",

                "date": parse_date_safe(
                    row.get("Date")
                ),

                "shift": clean_nan(
                    row.get("Shift")
                ),

                "mo": mo,
                "normalized_mo": normalized,

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
                ),

                "variant_name": mo
            })

    return records

# =========================================================
# DGBB PARSER
# =========================================================

def parse_dgbb_data(sheets):

    records = []

    for sheet_name, df in sheets.items():

        if sheet_name not in DGBB_LINE_SHEETS:
            continue

        if "MO" not in df.columns:
            continue

        for _, row in df.iterrows():

            mo = normalize_text(row.get("MO"))

            if not mo:
                continue

            normalized = extract_base_mo(mo)

            records.append({

                "source": "DGBB",
                "sheet": sheet_name,
                "department": "CHANNEL",
                "channel": "DGBB",

                "date": parse_date_safe(
                    row.get("Date")
                ),

                "shift": clean_nan(
                    row.get("Shift")
                ),

                "mo": mo,
                "normalized_mo": normalized,

                "dgbb_prefix": get_dgbb_prefix(normalized),

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
                ),

                "variant_name": mo
            })

    return records

# =========================================================
# TRACEABILITY PARSER
# =========================================================

def parse_traceability_data(sheets):

    records = []

    for sheet_name, df in sheets.items():

        if sheet_name not in TRACEABILITY_SHEETS:
            continue

        if "MO" not in df.columns:
            continue

        for _, row in df.iterrows():

            mo = normalize_text(row.get("MO"))

            if not mo:
                continue

            normalized = extract_base_mo(mo)

            records.append({

                "source": "TRACEABILITY",
                "sheet": sheet_name,
                "department": "CHANNEL OUT",

                "date": parse_date_safe(
                    row.get("Date")
                ),

                "mo": mo,
                "normalized_mo": normalized,

                "source_channel": normalize_text(
                    row.get("Source Channel")
                ),

                "production": clean_nan(
                    row.get("Production")
                ),

                "next_station": normalize_text(
                    row.get("Next_Station")
                ),

                "remark": normalize_text(
                    row.get("Remark")
                ),
            })

    return records

# =========================================================
# BUILD MASTER
# =========================================================

def build_mo_master(
    jobwork_records,
    trb_records,
    dgbb_records,
    traceability_records
):

    grouped = defaultdict(list)

    # -----------------------------------------------------
    # JOBWORK
    # -----------------------------------------------------

    for row in jobwork_records:

        grouped[row["normalized_mo"]].append(row)

    # -----------------------------------------------------
    # TRB MATCH
    # -----------------------------------------------------

    for trb in trb_records:

        matched = False

        for mo, rows in grouped.items():

            for jr in rows:

                if jr["source"] != "JOBWORK":
                    continue

                if (
                    mo in trb["normalized_mo"]
                    or trb["normalized_mo"] in mo
                ):

                    if within_date_window(
                        jr.get("date"),
                        trb.get("date"),
                        45
                    ):

                        grouped[mo].append(trb)
                        matched = True
                        break

            if matched:
                break

    # -----------------------------------------------------
    # DGBB MATCH
    # -----------------------------------------------------

    for dgbb in dgbb_records:

        matched = False

        dgbb_prefix = dgbb.get("dgbb_prefix")

        for mo, rows in grouped.items():

            if not mo.startswith(dgbb_prefix):
                continue

            for jr in rows:

                if jr["source"] != "JOBWORK":
                    continue

                if within_date_window(
                    jr.get("date"),
                    dgbb.get("date"),
                    45
                ):

                    grouped[mo].append(dgbb)
                    matched = True
                    break

            if matched:
                break

    # -----------------------------------------------------
    # TRACEABILITY MATCH
    # -----------------------------------------------------

    for trace in traceability_records:

        matched = False

        for mo, rows in grouped.items():

            for jr in rows:

                if jr["source"] != "JOBWORK":
                    continue

                if (
                    mo in trace["normalized_mo"]
                    or trace["normalized_mo"] in mo
                ):

                    if within_date_window(
                        jr.get("date"),
                        trace.get("date"),
                        60
                    ):

                        grouped[mo].append(trace)
                        matched = True
                        break

            if matched:
                break

    # -----------------------------------------------------
    # BUILD SUMMARY
    # -----------------------------------------------------

    master = []

    for mo, rows in grouped.items():

        rows.sort(
            key=lambda x: (
                x.get("date") or datetime.min.date(),
                str(x.get("source", ""))
            )
        )

        jobwork_rows = [
            x for x in rows
            if x["source"] == "JOBWORK"
        ]

        trb_rows = [
            x for x in rows
            if x["source"] == "TRB"
        ]

        dgbb_rows = [
            x for x in rows
            if x["source"] == "DGBB"
        ]

        trace_rows = [
            x for x in rows
            if x["source"] == "TRACEABILITY"
        ]

        all_dates = [
            x.get("date")
            for x in rows
            if x.get("date")
        ]

        start_date = None
        end_date = None

        if all_dates:

            start_date = min(all_dates)

            end_date = max(all_dates)

        approved_qty = sum([
            x.get("qty_approved") or 0
            for x in jobwork_rows
        ])

        returned_qty = sum([
            x.get("qty_returned") or 0
            for x in jobwork_rows
        ])

        trb_qty = sum([
            x.get("production") or 0
            for x in trb_rows
        ])

        dgbb_qty = sum([
            x.get("production") or 0
            for x in dgbb_rows
        ])

        output_qty = sum([
            x.get("production") or 0
            for x in trace_rows
        ])

        channels = []

        if trb_rows:
            channels.append("TRB")

        if dgbb_rows:
            channels.append("DGBB")

        ring_names = list(set([
            normalize_text(x.get("product"))
            for x in jobwork_rows
            if x.get("product")
        ]))

        master.append({

            "mo": mo,

            "start_date": start_date,

            "end_date": end_date,

            "approved_qty": approved_qty,

            "returned_qty": returned_qty,

            "channel_qty": trb_qty + dgbb_qty,

            "output_qty": output_qty,

            "channels": ", ".join(channels),

            "ring_names": ring_names,

            "records": len(rows),

            "status": (
                "Completed"
                if output_qty > 0
                else "Running"
            )
        })

    return master, grouped

# =========================================================
# CACHE
# =========================================================

MASTER_CACHE = None
FLOW_CACHE = None

# =========================================================
# MASTER API
# =========================================================

@router.get("/traceability_master")
def get_traceability_master(
    db: Session = Depends(get_db)
):

    global MASTER_CACHE
    global FLOW_CACHE

    try:

        if MASTER_CACHE is not None:

            return {
                "status": "success",
                "total_mo": len(MASTER_CACHE),
                "data": MASTER_CACHE
            }

        print("LOADING FILES")

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

        print("PARSING DATA")

        jobwork_records = parse_jobwork_data(
            jobwork_sheets
        )

        trb_records = parse_trb_data(
            trb_sheets
        )

        dgbb_records = parse_dgbb_data(
            dgbb_sheets
        )

        traceability_records = parse_traceability_data(
            trace_sheets
        )

        master, grouped = build_mo_master(
            jobwork_records,
            trb_records,
            dgbb_records,
            traceability_records
        )

        FLOW_CACHE = grouped

        MASTER_CACHE = sorted(
            master,
            key=lambda x: (
                x.get("start_date")
                or datetime.min.date()
            ),
            reverse=True
        )

        return {
            "status": "success",
            "total_mo": len(MASTER_CACHE),
            "data": MASTER_CACHE
        }

    except Exception as e:

        import traceback

        print(traceback.format_exc())

        raise HTTPException(
            status_code=500,
            detail=str(e)
        )

# =========================================================
# FLOW API
# =========================================================

@router.get("/traceability_flow/{mo}")
def get_traceability_flow(
    mo: str,
    db: Session = Depends(get_db)
):

    global FLOW_CACHE

    try:

        if FLOW_CACHE is None:

            get_traceability_master()

        normalized = extract_base_mo(mo)

        flow = FLOW_CACHE.get(normalized, [])

        flow.sort(
            key=lambda x: (
                x.get("date")
                or datetime.min.date()
            )
        )

        for row in flow:

            for key, value in row.items():

                try:

                    if isinstance(value, float):

                        if math.isnan(value):
                            row[key] = None

                except:
                    pass

        return {
            "status": "success",
            "mo": normalized,
            "records": flow
        }

    except Exception as e:

        import traceback

        print(traceback.format_exc())

        raise HTTPException(
            status_code=500,
            detail=str(e)
        )
