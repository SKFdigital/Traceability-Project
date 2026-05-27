from fastapi import APIRouter, HTTPException
import pandas as pd
import requests
import io
import threading
import time
from datetime import datetime
from settings import settings

router = APIRouter()

# =========================================================
# GLOBAL CACHE & THREADING CONFIG
# =========================================================
MASTER_CACHE = []
FLOW_CACHE = {}
LAST_REFRESH = None
IS_UPDATING = False
CACHE_DURATION_MINUTES = 5

# =========================================================
# SECURITY & CLEANING HELPERS
# =========================================================
def extract_mo_prefix(value):
    """Extracts the first 4 characters to group Jobwork and Channels perfectly (e.g., M108)"""
    if pd.isna(value):
        return ""
    return str(value).strip().upper().replace(" ", "")[:4]

def normalize_text(value):
    if pd.isna(value):
        return ""
    return str(value).strip()

def clean_nan(value):
    try:
        if pd.isna(value) or str(value).strip().lower() in ['nan', '-']:
            return 0
    except:
        pass
    try:
        return float(value)
    except:
        return 0

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
                # Force all columns to lowercase to avoid missing matches
                df.columns = [str(c).strip().lower() for c in df.columns]
                sheets[sheet] = df
            except Exception as e:
                print(f"Error reading sheet [{sheet}]: {str(e)}")
        return sheets
    except Exception as e:
        print(f"Failed to load workbook from {url}: {str(e)}")
        return {}

# =========================================================
# MAIN PROCESSING CORE LOGIC
# =========================================================
def process_traceability_data():
    global MASTER_CACHE, FLOW_CACHE, LAST_REFRESH, IS_UPDATING
    
    if IS_UPDATING:
        return
    
    IS_UPDATING = True
    print(f"[{datetime.now()}] STARTING BACKGROUND EXCEL CACHE REFRESH...")

    try:
        jobwork_sheets = load_excel_sheets(settings.JOBWORK_REPORT_URL)
        trb_sheets = load_excel_sheets(settings.TRB_MASTER_URL)
        dgbb_sheets = load_excel_sheets(settings.DGBB_MASTER_URL)

        # Grouping strictly by the first 4 characters (Prefix) to ensure SHO and Channels merge
        mo_records = {}

        # ---------------------------------------------------------
        # 1. PROCESS JOBWORK REPORT (SHO & Transit Buffer Individual)
        # ---------------------------------------------------------
        for sheet_name, df in jobwork_sheets.items():
            if "po / pr no." not in df.columns:
                continue

            for _, row in df.iterrows():
                raw_mo = row.get("po / pr no.")
                prefix = extract_mo_prefix(raw_mo)
                if not prefix: 
                    continue

                if prefix not in mo_records:
                    mo_records[prefix] = {
                        "full_mo": normalize_text(raw_mo),
                        "family": prefix,
                        "rows": []
                    }

                product = normalize_text(row.get("product"))
                jw_challan_date = parse_date_safe(row.get("jw challan date"))
                last_challan_date = parse_date_safe(row.get("last challan date"))
                qty_approved = clean_nan(row.get("qty approved"))
                qty_returned = clean_nan(row.get("qty returned"))
                status = normalize_text(row.get("current status"))

                # Create SHO Entry
                mo_records[prefix]["rows"].append({
                    "department": "SHO",
                    "product": product,
                    "in_date": "",
                    "out_date": str(last_challan_date) if last_challan_date else "",
                    "qty_in": qty_approved,
                    "qty_out": qty_returned,
                    "status": status
                })

                # Create Transit Buffer Entry
                mo_records[prefix]["rows"].append({
                    "department": "Transit Buffer",
                    "product": product,
                    "in_date": str(jw_challan_date) if jw_challan_date else "",
                    "out_date": str(last_challan_date) if last_challan_date else "",
                    "qty_in": qty_returned, 
                    "qty_out": qty_returned,
                    "status": status
                })

        # ---------------------------------------------------------
        # INSERT CUMULATIVE SUMMARY ROWS FOR SHO & TRANSIT BUFFER
        # ---------------------------------------------------------
        for prefix, data in mo_records.items():
            sho_rows = [r for r in data["rows"] if r["department"] == "SHO"]
            tb_rows = [r for r in data["rows"] if r["department"] == "Transit Buffer"]

            if sho_rows:
                sho_total_in = sum(r["qty_in"] for r in sho_rows)
                sho_total_out = sum(r["qty_out"] for r in sho_rows)
                data["rows"].append({
                    "department": "SHO (Total)",
                    "product": "All Types Combined",
                    "in_date": "",
                    "out_date": "",
                    "qty_in": sho_total_in,
                    "qty_out": sho_total_out,
                    "status": "Aggregated"
                })

            if tb_rows:
                tb_total_in = sum(r["qty_in"] for r in tb_rows)
                tb_total_out = sum(r["qty_out"] for r in tb_rows)
                data["rows"].append({
                    "department": "Transit Buffer (Total)",
                    "product": "All Types Combined",
                    "in_date": "",
                    "out_date": "",
                    "qty_in": tb_total_in,
                    "qty_out": tb_total_out,
                    "status": "Aggregated"
                })

        # ---------------------------------------------------------
        # 2. PROCESS CHANNELS (TRB Master & DGBB Master Subsheets)
        # ---------------------------------------------------------
        all_channels = {**trb_sheets, **dgbb_sheets}
        channel_aggregation = {}

        for channel_name, df in all_channels.items():
            if "mo" not in df.columns:
                continue

            type_col = "type" if "type" in df.columns else ("product" if "product" in df.columns else None)

            for _, row in df.iterrows():
                raw_mo = row.get("mo")
                prefix = extract_mo_prefix(raw_mo)
                if not prefix:
                    continue

                prod_type = normalize_text(row.get(type_col)) if type_col else "Unknown Type"
                production = clean_nan(row.get("production"))
                cumulative = clean_nan(row.get("cumulative production"))
                date_val = parse_date_safe(row.get("date"))

                # Aggregate by Prefix + Exact Channel Name + Product Type
                agg_key = (prefix, channel_name, prod_type)

                if agg_key not in channel_aggregation:
                    channel_aggregation[agg_key] = {
                        "raw_mo_string": normalize_text(raw_mo),
                        "first_date": None,
                        "max_cum_date": None,
                        "max_cumulative": 0.0
                    }

                agg = channel_aggregation[agg_key]

                if production > 0 and production == cumulative:
                    if not agg["first_date"] or (date_val and date_val < agg["first_date"]):
                        agg["first_date"] = date_val

                if cumulative > agg["max_cumulative"]:
                    agg["max_cumulative"] = cumulative
                    agg["max_cum_date"] = date_val
                elif cumulative == agg["max_cumulative"] and agg["max_cumulative"] > 0:
                    if date_val and (not agg["max_cum_date"] or date_val > agg["max_cum_date"]):
                        agg["max_cum_date"] = date_val

        # Push processed channel records back into global tracking map
        for (prefix, channel_name, prod_type), metrics in channel_aggregation.items():
            if prefix not in mo_records:
                mo_records[prefix] = {
                    "full_mo": metrics["raw_mo_string"],
                    "family": prefix,
                    "rows": []
                }

            in_d_str = str(metrics["first_date"]) if metrics["first_date"] else ""
            out_d_str = str(metrics["max_cum_date"]) if metrics["max_cum_date"] else ""
            max_qty = metrics["max_cumulative"]

            mo_records[prefix]["rows"].append({
                "department": channel_name, 
                "product": prod_type,
                "in_date": in_d_str,
                "out_date": out_d_str,
                "qty_in": max_qty,
                "qty_out": max_qty,
                "status": "Completed" if max_qty > 0 else "Running"
            })

        # ---------------------------------------------------------
        # 3. COMPILE STRUCTURED QUICK CACHE
        # ---------------------------------------------------------
        new_master = []
        new_flow = {}

        for prefix, data in mo_records.items():
            # For master KPI stats, safely grab from calculated summary row values if available
            sho_sum = sum(r["qty_in"] for r in data["rows"] if r["department"] == "SHO")
            channel_sum = sum(r["qty_out"] for r in data["rows"] if r["department"] not in ["SHO", "Transit Buffer", "SHO (Total)", "Transit Buffer (Total)"])

            new_master.append({
                "mo": data["full_mo"],
                "family": data["family"],
                "sho_qty": sho_sum,
                "channel_qty": channel_sum,
                "stage_count": len(data["rows"])
            })

            new_flow[prefix] = {
                "mo": data["full_mo"],
                "family": data["family"],
                "flow_data": data["rows"]
            }

        MASTER_CACHE = new_master
        FLOW_CACHE = new_flow
        LAST_REFRESH = datetime.now()
        print(f"[{datetime.now()}] BACKGROUND REFRESH SUCCESSFUL. {len(MASTER_CACHE)} UNIQUE MO FAMILIES INDEXED.")

    except Exception as e:
        print(f"CRITICAL ERROR ENCOUNTERED IN BACKGROUND THREAD: {str(e)}")
    finally:
        IS_UPDATING = False

# =========================================================
# BACKGROUND DAEMON INITIALIZATION
# =========================================================
def background_refresh_loop():
    process_traceability_data()
    while True:
        time.sleep(CACHE_DURATION_MINUTES * 60)
        process_traceability_data()

t = threading.Thread(target=background_refresh_loop, daemon=True)
t.start()

# =========================================================
# ROUTER API ENDPOINTS
# =========================================================
@router.get("/traceability_all_mos")
def get_all_mos():
    if not LAST_REFRESH and not MASTER_CACHE:
        raise HTTPException(status_code=503, detail="System initializing pipeline cache, please retry in 10 seconds...")
    return {
        "status": "success",
        "last_updated": str(LAST_REFRESH),
        "data": MASTER_CACHE
    }

@router.get("/traceability_report/{mo}")
def get_flow(mo: str):
    search_prefix = extract_mo_prefix(mo)
    
    if search_prefix in FLOW_CACHE:
        return {
            "status": "success",
            "last_updated": str(LAST_REFRESH),
            "data": FLOW_CACHE[search_prefix]
        }

    raise HTTPException(status_code=404, detail=f"No traceability logs matched for order criteria ID: '{mo}'")
