from fastapi import APIRouter, HTTPException
import pandas as pd
import requests
import io
import threading
import time
import math
from datetime import datetime
from settings import settings

router = APIRouter()

# =========================================================
# GLOBAL CACHE & THREADING CONFIG (TBE ISOLATED)
# =========================================================
TBE_MASTER_CACHE = []
TBE_FLOW_CACHE = {}
LAST_TBE_REFRESH = None
IS_TBE_UPDATING = False
CACHE_DURATION_MINUTES = 5

# =========================================================
# SECURITY, CLEANING & PARSING HELPERS
# =========================================================
def clean_mo(value):
    if pd.isna(value):
        return None
        
    val = str(value).strip().upper().replace(" ", "").replace(".0", "")
    
    if val in ["NAN", "-", "...", ""] or len(val) < 4:
        return None
        
    return val

def get_mo_group(clean_mo_str):
    if clean_mo_str and len(clean_mo_str) >= 4:
        return clean_mo_str[:4]
    return clean_mo_str

def normalize_text(value):
    if pd.isna(value):
        return ""
    return str(value).strip()

def clean_nan(value):
    try:
        if pd.isna(value) or str(value).strip().lower() in ['nan', '-', '...', '']:
            return 0.0
        f_val = float(value)
        if math.isnan(f_val):
            return 0.0
        return f_val
    except:
        return 0.0

def parse_date_safe(value):
    try:
        if pd.isna(value) or str(value).strip().lower() in ["nan", "nat", "", "-"]:
            return None
        parsed = pd.to_datetime(value, errors='coerce', dayfirst=True)
        if pd.isna(parsed):
            return None
        return parsed.date()
    except:
        return None

def parse_product_details(prod_text):
    text = normalize_text(prod_text).upper()
    component = "IM" if "IM" in text or "IR" in text else ("OM" if "OM" in text or "OR" in text else "Assembly")
    base_product = text if text else "Gen Product"
    return base_product, component

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
                df.columns = [str(c).strip().lower() for c in df.columns]
                sheets[sheet] = df
            except Exception as e:
                print(f"Error reading sheet [{sheet}]: {str(e)}")
        return sheets
    except Exception as e:
        print(f"Failed to load workbook from {url}: {str(e)}")
        return {}

# =========================================================
# MAIN TBE PROCESSING CORE LOGIC
# =========================================================
def process_tbe_data():
    global TBE_MASTER_CACHE, TBE_FLOW_CACHE, LAST_TBE_REFRESH, IS_TBE_UPDATING
    
    if IS_TBE_UPDATING:
        return
    
    IS_TBE_UPDATING = True
    print(f"[{datetime.now()}] STARTING BACKGROUND TBE EXCEL CACHE REFRESH...")

    try:
        # NOTE: Ensure TBE_MASTER_URL is added to your settings.py
        tbe_sheets = load_excel_sheets(settings.TBE_MASTER_URL)
        
        tbe_flow_records = {}
        tbe_aggregation = {}

        # ---------------------------------------------------------
        # TBE CALIBRATION LOGIC - Prioritizing Channel MO as Ground Truth
        # ---------------------------------------------------------
        for sheet_name, df in tbe_sheets.items():
            
            # Searching for the exact TBE column mappings
            mo_col = "mo" if "mo" in df.columns else ("mo#" if "mo#" in df.columns else None)
            if not mo_col:
                continue

            for _, row in df.iterrows():
                raw_mo = clean_mo(row.get(mo_col))
                if not raw_mo:
                    continue
                
                mo_group = get_mo_group(raw_mo)
                
                # Extracting specific TBE metrics
                date_val = parse_date_safe(row.get("date"))
                shift = normalize_text(row.get("shift"))
                channel_id = normalize_text(row.get("ch#"))
                prod_type = normalize_text(row.get("type"))
                base_prod, comp_type = parse_product_details(prod_type)
                
                # Weight and Ring Counts
                gross_wt = clean_nan(row.get("gross weight"))
                net_wt = clean_nan(row.get("net weight"))
                ring_wt = clean_nan(row.get("ring weight"))
                num_rings = clean_nan(row.get("number of rings"))

                # 1. Store Flow Records (Timeline)
                if mo_group not in tbe_flow_records:
                    tbe_flow_records[mo_group] = {"mo": mo_group, "rows": []}

                tbe_flow_records[mo_group]["rows"].append({
                    "department": f"TBE Channel {channel_id}", 
                    "product": prod_type,
                    "date": str(date_val) if date_val else "-",
                    "shift": shift,
                    "gross_weight": gross_wt,
                    "net_weight": net_wt,
                    "ring_weight": ring_wt,
                    "rings": num_rings,
                    "status": "Calibrated" if num_rings > 0 else "Pending Audit"
                })
                
                # 2. Aggregate Master Summary by MO, Channel, and Product Family
                sum_key = (mo_group, channel_id, base_prod, comp_type)
                
                if sum_key not in tbe_aggregation:
                    tbe_aggregation[sum_key] = {
                        "mo": mo_group,
                        "channel": channel_id,
                        "base_product": base_prod,
                        "component_type": comp_type,
                        "total_rings": 0.0,
                        "total_net_weight": 0.0,
                        "first_date": date_val,
                        "last_date": date_val
                    }
                
                agg = tbe_aggregation[sum_key]
                agg["total_rings"] += num_rings
                agg["total_net_weight"] += net_wt
                
                if date_val:
                    agg["first_date"] = min(agg["first_date"], date_val) if agg["first_date"] else date_val
                    agg["last_date"] = max(agg["last_date"], date_val) if agg["last_date"] else date_val

        # ---------------------------------------------------------
        # COMPILING FINAL TBE CACHE & SORTING
        # ---------------------------------------------------------
        compiled_summary = []
        for (mo_group, channel_id, base_prod, comp_type), agg in tbe_aggregation.items():
            compiled_summary.append({
                "mo": mo_group,
                "channel": channel_id,
                "base_product": base_prod,
                "component_type": comp_type,
                "total_rings": int(agg["total_rings"]),
                "total_net_weight": round(agg["total_net_weight"], 2),
                "in_date": str(agg["first_date"]) if agg["first_date"] else "-",
                "out_date": str(agg["last_date"]) if agg["last_date"] else "-",
                "status": "Production Complete" if agg["total_rings"] > 0 else "In Queue"
            })
            
        compiled_summary.sort(key=lambda x: (x["mo"], x["channel"], x["component_type"]))
        
        TBE_MASTER_CACHE = compiled_summary
        TBE_FLOW_CACHE = tbe_flow_records
        LAST_TBE_REFRESH = datetime.now()
        print(f"[{datetime.now()}] TBE PIPELINE SYNCHRONIZED. CACHE INSTANCED.")

    except Exception as e:
        print(f"CRITICAL TBE DATA ENGINE THREAD ERROR: {str(e)}")
    finally:
        IS_TBE_UPDATING = False

# Background Daemon initialization for TBE
def background_tbe_refresh_loop():
    process_tbe_data()
    while True:
        time.sleep(CACHE_DURATION_MINUTES * 60)
        process_tbe_data()

t = threading.Thread(target=background_tbe_refresh_loop, daemon=True)
t.start()

# =========================================================
# TBE ROUTER API SERVICE ENDPOINTS
# =========================================================
@router.get("/tbe_all_mos")
def get_all_tbe_mos():
    if not LAST_TBE_REFRESH and not TBE_MASTER_CACHE:
        return {
            "status": "initializing",
            "message": "TBE Calibration Maps are being prepared. Please hold...",
            "data": []
        }
    return {
        "status": "success",
        "last_updated": str(LAST_TBE_REFRESH),
        "data": TBE_MASTER_CACHE
    }

@router.get("/tbe_report/{mo}")
def get_tbe_flow(mo: str):
    search_mo = get_mo_group(clean_mo(mo))
    if search_mo in TBE_FLOW_CACHE:
        return {
            "status": "success",
            "last_updated": str(LAST_TBE_REFRESH),
            "data": TBE_FLOW_CACHE[search_mo]
        }
    raise HTTPException(status_code=404, detail=f"No TBE calibration tracking found for MO parameter: '{mo}'")
