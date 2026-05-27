from fastapi import APIRouter, HTTPException
import pandas as pd
import requests
import io
import re
import threading
import time
from datetime import datetime
from settings import settings

router = APIRouter()

# =========================================================
# GLOBAL CACHE & THREADING
# =========================================================
MASTER_CACHE = []
FLOW_CACHE = {}
LAST_REFRESH = None
IS_UPDATING = False
CACHE_DURATION_MINUTES = 5

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
            return 0
    except:
        pass
    return float(value) if value else 0

def parse_date_safe(value):
    try:
        if pd.isna(value):
            return None
        parsed = pd.to_datetime(value, errors='coerce', dayfirst=True)
        if pd.isna(parsed):
            return None
        return parsed.date()
    except:
        return None

def extract_mo_prefix(text):
    if not text:
        return ""
    text = str(text).upper().replace(" ", "")
    # Extracts the first 4 characters (e.g., M108)
    return text[:4]

def download_excel(url):
    response = requests.get(url)
    if response.status_code != 200:
        raise Exception(f"Failed downloading excel from {url}")
    return io.BytesIO(response.content)

def load_excel_sheets(url):
    try:
        excel_data = download_excel(url)
        xls = pd.ExcelFile(excel_data)
        sheets = {}
        for sheet in xls.sheet_names:
            try:
                df = pd.read_excel(xls, sheet_name=sheet)
                df.columns = [str(c).strip() for c in df.columns]
                sheets[sheet] = df
            except Exception as e:
                print(f"FAILED SHEET: {sheet}, Error: {str(e)}")
        return sheets
    except Exception as e:
        print(f"FAILED TO LOAD WORKBOOK: {url}, Error: {str(e)}")
        return {}

# =========================================================
# CORE PROCESSING LOGIC
# =========================================================
def process_traceability_data():
    global MASTER_CACHE, FLOW_CACHE, LAST_REFRESH, IS_UPDATING
    
    if IS_UPDATING:
        return
    
    IS_UPDATING = True
    print(f"[{datetime.now()}] REFRESHING TRACEABILITY CACHE (BACKGROUND)...")

    try:
        # 1. Load Files (Traceability Master dropped as per requirement)
        jobwork_sheets = load_excel_sheets(settings.JOBWORK_REPORT_URL)
        trb_sheets = load_excel_sheets(settings.TRB_MASTER_URL)
        dgbb_sheets = load_excel_sheets(settings.DGBB_MASTER_URL)

        # Temp dictionaries to build the final structures
        # Grouped by MO Prefix (First 4 chars)
        mo_grouping = {}
        channel_tracker = {}

        # ---------------------------------------------------------
        # PROCESS JOBWORK (SHO & Transit Buffer)
        # ---------------------------------------------------------
        for sheet_name, df in jobwork_sheets.items():
            if "PO / PR No." not in df.columns:
                continue

            for _, row in df.iterrows():
                mo = normalize_text(row.get("PO / PR No."))
                prefix = extract_mo_prefix(mo)
                if not prefix: continue

                if prefix not in mo_grouping:
                    mo_grouping[prefix] = {"mo": mo, "family": prefix, "rows": []}

                product = normalize_text(row.get("Product"))
                jw_challan_date = parse_date_safe(row.get("JW Challan Date"))
                last_challan_date = parse_date_safe(row.get("Last Challan Date"))
                qty_approved = clean_nan(row.get("Qty Approved"))
                qty_returned = clean_nan(row.get("Qty Returned"))
                status = normalize_text(row.get("Current Status"))

                # SHO Row
                mo_grouping[prefix]["rows"].append({
                    "department": "SHO",
                    "product": product,
                    "in_date": "", # Keep empty per requirement
                    "out_date": str(last_challan_date) if last_challan_date else "",
                    "qty_in": qty_approved,
                    "qty_out": qty_returned,
                    "status": status
                })

                # Transit Buffer Row
                mo_grouping[prefix]["rows"].append({
                    "department": "Transit Buffer",
                    "product": product,
                    "in_date": str(jw_challan_date) if jw_challan_date else "",
                    "out_date": str(last_challan_date) if last_challan_date else "",
                    "qty_in": qty_returned, # Qty Returned for both in Transit Buffer
                    "qty_out": qty_returned,
                    "status": status
                })

        # ---------------------------------------------------------
        # PROCESS CHANNELS (TRB & DGBB)
        # ---------------------------------------------------------
        all_channel_sheets = {**trb_sheets, **dgbb_sheets}
        
        for sheet_name, df in all_channel_sheets.items():
            if "MO" not in df.columns:
                continue
            
            # Find the type/product column name (Usually 'Type', check alternatives just in case)
            type_col = "Type" if "Type" in df.columns else ("Product" if "Product" in df.columns else None)

            for _, row in df.iterrows():
                mo = normalize_text(row.get("MO"))
                prefix = extract_mo_prefix(mo)
                if not prefix: continue

                # Allow capturing MOs that ONLY exist in Channel (External Suppliers)
                if prefix not in channel_tracker:
                    channel_tracker[prefix] = {}
                    if prefix not in mo_grouping:
                        mo_grouping[prefix] = {"mo": mo, "family": prefix, "rows": []}

                prod_type = normalize_text(row.get(type_col)) if type_col else "Unknown"
                
                # We need to track the first production date and max cumulative production
                production = clean_nan(row.get("Production"))
                cumulative = clean_nan(row.get("Cumulative production"))
                date_val = parse_date_safe(row.get("Date"))

                if prod_type not in channel_tracker[prefix]:
                    channel_tracker[prefix][prod_type] = {
                        "first_date": None,
                        "max_cum_date": None,
                        "max_cumulative": 0
                    }

                tracker = channel_tracker[prefix][prod_type]

                # Update First Date (Production == Cumulative && Production > 0)
                if production > 0 and production == cumulative:
                    if not tracker["first_date"] or (date_val and date_val < tracker["first_date"]):
                        tracker["first_date"] = date_val

                # Update Max Cumulative & Its Date
                if cumulative > tracker["max_cumulative"]:
                    tracker["max_cumulative"] = cumulative
                    tracker["max_cum_date"] = date_val

        # Compile Channel Data into Rows
        for prefix, types_dict in channel_tracker.items():
            for prod_type, metrics in types_dict.items():
                first_d = str(metrics["first_date"]) if metrics["first_date"] else ""
                max_d = str(metrics["max_cum_date"]) if metrics["max_cum_date"] else ""
                max_qty = metrics["max_cumulative"]

                mo_grouping[prefix]["rows"].append({
                    "department": "Channel",
                    "product": prod_type,
                    "in_date": first_d,
                    "out_date": max_d,
                    "qty_in": max_qty,
                    "qty_out": max_qty,
                    "status": "Completed" if max_qty > 0 else "Running"
                })

        # ---------------------------------------------------------
        # FINALIZE CACHE
        # ---------------------------------------------------------
        new_master = []
        new_flow = {}

        for prefix, data in mo_grouping.items():
            # Summarize for Dashboard (using basic derived values)
            total_qty_in = sum(r["qty_in"] for r in data["rows"] if r["department"] == "SHO")
            total_channel = sum(r["qty_out"] for r in data["rows"] if r["department"] == "Channel")

            new_master.append({
                "mo": data["mo"],
                "family": data["family"],
                "sho_qty": total_qty_in,
                "channel_qty": total_channel,
                "stage_count": len(data["rows"])
            })

            new_flow[prefix] = {
                "mo": data["mo"],
                "family": data["family"],
                "flow_data": data["rows"]
            }

        MASTER_CACHE = new_master
        FLOW_CACHE = new_flow
        LAST_REFRESH = datetime.now()

        print(f"[{datetime.now()}] CACHE REFRESH DONE. {len(MASTER_CACHE)} MOs Loaded.")
    
    except Exception as e:
        print(f"ERROR IN BACKGROUND REFRESH: {str(e)}")
    
    finally:
        IS_UPDATING = False

# =========================================================
# BACKGROUND DAEMON LOOP
# =========================================================
def background_refresh_loop():
    # Initial load immediately
    process_traceability_data()
    # Continuous loop
    while True:
        time.sleep(CACHE_DURATION_MINUTES * 60)
        process_traceability_data()

# Start the background thread when this module loads
t = threading.Thread(target=background_refresh_loop, daemon=True)
t.start()

# =========================================================
# APIS
# =========================================================
@router.get("/traceability_all_mos")
def get_all_mos():
    if not LAST_REFRESH and not MASTER_CACHE:
        # Fallback if accessed before thread finishes first run
        raise HTTPException(status_code=503, detail="System initializing, please wait a few seconds...")
        
    return {
        "status": "success",
        "last_updated": str(LAST_REFRESH),
        "count": len(MASTER_CACHE),
        "data": MASTER_CACHE
    }

@router.get("/traceability_report/{mo}")
def get_flow(mo: str):
    # Match the MO by prefix so exact full MO strings or short family strings both work
    prefix = extract_mo_prefix(mo)
    
    if prefix not in FLOW_CACHE:
        raise HTTPException(status_code=404, detail="MO not found")

    return {
        "status": "success",
        "last_updated": str(LAST_REFRESH),
        "data": FLOW_CACHE[prefix]
    }
