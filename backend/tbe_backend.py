from fastapi import APIRouter, HTTPException
import pandas as pd
import requests
import io
import threading
import time
import re
import math
from datetime import datetime
from settings import settings # Ensure settings has RING_WT_URL instead of JOBWORK_REPORT_URL

router = APIRouter()

# =========================================================
# GLOBAL CACHE & THREADING CONFIG
# =========================================================
MASTER_CACHE = []
LAST_REFRESH = None
IS_UPDATING = False
CACHE_DURATION_MINUTES = 5

# =========================================================
# SECURITY, CLEANING & PARSING HELPERS
# =========================================================
def clean_mo(value):
    if pd.isna(value): return None
    val = str(value).strip().upper().replace(" ", "").replace(".0", "")
    if val in ["NAN", "-", "...", ""] or len(val) < 4: return None
    return val

def normalize_text(value):
    if pd.isna(value): return ""
    return str(value).strip().upper()

def clean_nan(value):
    try:
        if pd.isna(value) or str(value).strip().lower() in ['nan', '-', '...', '']: return 0.0
        f_val = float(value)
        if math.isnan(f_val): return 0.0
        return f_val
    except:
        return 0.0

def parse_date_safe(value):
    try:
        if pd.isna(value) or str(value).strip().lower() in ["nan", "nat", "", "-"]: return None
        parsed = pd.to_datetime(value, errors='coerce', dayfirst=True)
        if pd.isna(parsed): return None
        return parsed.date()
    except:
        return None

def parse_family_and_type(text):
    """
    Extracts the pure Bearing Family and the IM/OM component type.
    Strips IM/OM out to isolate the exact family name. No generic grouping text.
    """
    text = normalize_text(text)
    
    # Determine Type
    component = "IM" if "IM" in text or "IR" in text else ("OM" if "OM" in text or "OR" in text else "Assembly")
    
    # Extract clean Family
    family = text.replace("IM", "").replace("OM", "").replace("IR", "").replace("OR", "").strip()
    # Remove any trailing hyphens/spaces to make matching robust
    family = re.sub(r'[^A-Z0-9]', '', family) if family else "UNKNOWN_FAMILY"
    
    return family, component

def download_excel(url):
    response = requests.get(url)
    if response.status_code != 200: raise Exception(f"Failed downloading excel from {url}")
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
                pass
        return sheets
    except Exception:
        return {}

# =========================================================
# MAIN PROCESSING CORE LOGIC
# =========================================================
def process_tbe_data():
    global MASTER_CACHE, LAST_REFRESH, IS_UPDATING
    
    if IS_UPDATING: return
    IS_UPDATING = True
    print(f"[{datetime.now()}] STARTING TBE EXCEL CACHE REFRESH...")

    try:
        mo_sheets = load_excel_sheets(settings.MO_DATA_URL)
        ring_wt_sheets = load_excel_sheets(settings.RINGWT_TRANSITBUFFER_URL) # NEW PRIORITY SHEET
        trb_sheets = load_excel_sheets(settings.TRB_MASTER_URL)
        dgbb_sheets = load_excel_sheets(settings.DGBB_MASTER_URL)

        # ---------------------------------------------------------
        # 1. PARSE CHANNELS (TRB & DGBB) - Find Max & Min Dates per Channel+Family
        # ---------------------------------------------------------
        all_channels = {**trb_sheets, **dgbb_sheets}
        channel_data = {} # Key: (Channel, Family) -> Data

        for sheet_name, df in all_channels.items():
            if "channel number" not in df.columns: continue
            type_col = "type" if "type" in df.columns else ("product" if "product" in df.columns else None)
            if not type_col: continue

            for _, row in df.iterrows():
                channel_num = normalize_text(row.get("channel number"))
                prod_str = row.get(type_col)
                family, _ = parse_family_and_type(prod_str)
                if not channel_num or not family: continue

                cumulative = clean_nan(row.get("cumulative production"))
                production = clean_nan(row.get("production"))
                date_val = parse_date_safe(row.get("date"))

                c_key = (channel_num, family)
                if c_key not in channel_data:
                    channel_data[c_key] = {"max_cum": 0.0, "in_date": None, "out_date": None}
                
                c_meta = channel_data[c_key]
                if cumulative > c_meta["max_cum"]:
                    c_meta["max_cum"] = cumulative
                
                if date_val:
                    # In Date logic (1st prod start when prod == cumulative)
                    if production > 0 and production == cumulative:
                        c_meta["in_date"] = min(c_meta["in_date"], date_val) if c_meta["in_date"] else date_val
                    # Out date logic (max date of cumulative)
                    c_meta["out_date"] = max(c_meta["out_date"], date_val) if c_meta["out_date"] else date_val

        # ---------------------------------------------------------
        # 2. PARSE MO_DATA - Get Target Qty & MO Number by Family
        # ---------------------------------------------------------
        mo_dict = {} # Key: Family -> {MO, Target}
        for sheet_name, df in mo_sheets.items():
            for _, row in df.iterrows():
                mo_num = clean_mo(row.get("mo#", row.get("mo number")))
                prod_val = row.get("finalvariant", row.get("product"))
                family, _ = parse_family_and_type(prod_val)
                target = clean_nan(row.get("qty req", row.get("target qty")))
                
                if family and mo_num:
                    mo_dict[family] = {"mo": mo_num, "target": target}

        # ---------------------------------------------------------
        # 3. PARSE RING WT TRANSIT BUFFER (THE PRIORITY BASE)
        # ---------------------------------------------------------
        ring_wt_aggregated = {} # Key: (Channel, Family, IM/OM)
        
        for sheet_name, df in ring_wt_sheets.items():
            if "channel number" not in df.columns: continue
            type_col = "type" if "type" in df.columns else ("product" if "product" in df.columns else None)
            
            for _, row in df.iterrows():
                channel_num = normalize_text(row.get("channel number"))
                prod_str = row.get(type_col)
                family, comp_type = parse_family_and_type(prod_str)
                if not channel_num or not family: continue

                qty = clean_nan(row.get("qty"))
                date_val = parse_date_safe(row.get("date"))

                r_key = (channel_num, family, comp_type)
                if r_key not in ring_wt_aggregated:
                    ring_wt_aggregated[r_key] = {"qty": 0.0, "max_date": None}
                
                ring_wt_aggregated[r_key]["qty"] += qty
                if date_val:
                    ring_wt_aggregated[r_key]["max_date"] = max(ring_wt_aggregated[r_key]["max_date"], date_val) if ring_wt_aggregated[r_key]["max_date"] else date_val

        # ---------------------------------------------------------
        # 4. COMPILE FINAL ROWS (Merging Everything)
        # ---------------------------------------------------------
        compiled_summary = []
        
        for (channel_num, family, comp_type), rw_data in ring_wt_aggregated.items():
            # Match Channel Data
            c_key = (channel_num, family)
            ch_info = channel_data.get(c_key, {"max_cum": None, "in_date": None, "out_date": None})
            
            # Match MO Data
            mo_info = mo_dict.get(family, {"mo": "", "target": None})
            
            # Status Logic based on Transit Buffer & Channel quantities
            calc_status = "In Process"
            if ch_info["max_cum"] and ch_info["max_cum"] >= rw_data["qty"] and rw_data["qty"] > 0:
                calc_status = "Completed"
            elif rw_data["qty"] == 0 and not ch_info["max_cum"]:
                calc_status = "Yet to Start"

            compiled_summary.append({
                "mo_number": mo_info["mo"],
                "product_variant": family,      # STRICTLY using Exact Family
                "target_qty": mo_info["target"] if mo_info["target"] else "",
                "ring_type": comp_type,
                "sho_qty": rw_data["qty"],
                "sho_in": "",                   # Kept empty as per rule
                "tb_qty": rw_data["qty"],       # Similar to SHO
                "tb_out": str(rw_data["max_date"]) if rw_data["max_date"] else "-",
                "ch_qty": ch_info["max_cum"] if ch_info["max_cum"] else "",
                "ch_in": str(ch_info["in_date"]) if ch_info["in_date"] else "",
                "ch_out": str(ch_info["out_date"]) if ch_info["out_date"] else "",
                "status": calc_status,
                "channel_ref": channel_num      # Hidden grouping key
            })

        # Sort by MO, then Family, then Ring Type so IM/OM sit together
        compiled_summary.sort(key=lambda x: (x["mo_number"], x["product_variant"], x["ring_type"]))
        
        MASTER_CACHE = compiled_summary
        LAST_REFRESH = datetime.now()
        print(f"[{datetime.now()}] TBE PIPELINE SYNCHRONIZED.")

    except Exception as e:
        print(f"CRITICAL DATA ENGINE ERROR: {str(e)}")
    finally:
        IS_UPDATING = False

# Background Daemon
def background_refresh_loop():
    process_tbe_data()
    while True:
        time.sleep(CACHE_DURATION_MINUTES * 60)
        process_tbe_data()

t = threading.Thread(target=background_refresh_loop, daemon=True)
t.start()

# =========================================================
# ROUTER API SERVICE ENDPOINTS
# =========================================================
@router.get("/tbe_all_mos")
def get_tbe_data():
    if not LAST_REFRESH and not MASTER_CACHE:
        return {
            "status": "initializing",
            "message": "System is parsing Transit Buffers. Please hold...",
            "data": []
        }
    return {
        "status": "success",
        "data": MASTER_CACHE
    }
