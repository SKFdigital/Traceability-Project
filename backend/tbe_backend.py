from fastapi import APIRouter, HTTPException
import pandas as pd
import requests
import io
import threading
import time
import re
import math
from datetime import datetime
from settings import settings

router = APIRouter()

# =========================================================
# GLOBAL CACHE & THREADING CONFIG
# =========================================================
MASTER_CACHE = []
LAST_REFRESH = None
IS_UPDATING = False
CACHE_DURATION_MINUTES = 5

# =========================================================
# FUZZY MATCHING & ULTRA-SAFE CLEANING HELPERS
# =========================================================
def find_column(df, patterns):
    """
    Fuzzy searches dataframe columns for loose keyword matches.
    Prevents crashing/skipping if headers have minor label updates.
    """
    for col in df.columns:
        col_clean = str(col).strip().lower()
        for pattern in patterns:
            if pattern in col_clean:
                return col
    return None

def clean_mo(value):
    if pd.isna(value): return ""
    val = str(value).strip().upper().replace(" ", "").split('.')[0]
    if val in ["NAN", "-", "...", ""] or len(val) < 4: return ""
    return val

def normalize_text(value):
    if pd.isna(value): return ""
    return str(value).strip().upper()

def normalize_channel(value):
    """
    Forces channel names into clean alphanumeric strings.
    Converts float variants like '4.0' or '04' uniformly to '4'.
    """
    if pd.isna(value): return ""
    val_str = str(value).strip().upper()
    # Strip decimals if interpreted as a float
    if val_str.endswith(".0"):
        val_str = val_str[:-2]
    # Strip leading zeros to ensure uniform join alignment
    val_str = val_str.lstrip("0")
    return val_str if val_str else "0"

def clean_nan(value):
    try:
        if pd.isna(value) or str(value).strip().lower() in ['nan', '-', '...', '']: 
            return 0.0
        return float(value)
    except:
        return 0.0

def parse_date_safe(value):
    try:
        if pd.isna(value) or str(value).strip().lower() in ["nan", "nat", "", "-"]: 
            return None
        parsed = pd.to_datetime(value, errors='coerce', dayfirst=True)
        if pd.isna(parsed): return None
        return parsed.date()
    except:
        return None

def parse_family_and_type(prod_text):
    """
    Isolates exact bearing family name from the component text.
    Handles prefixes and suffixes safely without corrupting base model strings.
    """
    text = normalize_text(prod_text)
    if not text: 
        return "UNKNOWN_FAMILY", "Assembly"
        
    component = "Assembly"
    if "IM" in text or "IR" in text:
        component = "IM"
    elif "OM" in text or "OR" in text:
        component = "OM"
        
    clean = text
    # Strip component structural markers cleanly from boundary targets
    for pfx in ["IM-", "OM-", "IR-", "OR-", "IM", "OM", "IR", "OR"]:
        if clean.startswith(pfx):
            clean = clean[len(pfx):]
            break
    for sfx in ["-IM", "-OM", "-IR", "-OR", "IM", "OM", "IR", "OR"]:
        if clean.endswith(sfx):
            clean = clean[:-len(sfx)]
            break
            
    clean = clean.strip(" -_")
    return (clean if clean else text), component

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
            except:
                pass
        return sheets
    except:
        return {}

# =========================================================
# MAIN PROCESSING CORE LOGIC
# =========================================================
def process_tbe_data():
    global MASTER_CACHE, LAST_REFRESH, IS_UPDATING
    
    if IS_UPDATING: return
    IS_UPDATING = True
    print(f"[{datetime.now()}] STARTING TBE FUZZY-MATCH ENGAGEMENT ENGINE...")

    try:
        mo_sheets = load_excel_sheets(settings.MO_DATA_URL)
        ring_wt_sheets = load_excel_sheets(settings.RINGWT_TRANSITBUFFER_URL)
        trb_sheets = load_excel_sheets(settings.TRB_MASTER_URL)
        dgbb_sheets = load_excel_sheets(settings.DGBB_MASTER_URL)

        # ---------------------------------------------------------
        # 1. PARSE CHANNELS (TRB & DGBB MASTER DATA)
        # ---------------------------------------------------------
        all_channels = {**trb_sheets, **dgbb_sheets}
        channel_data = {}

        for sheet_name, df in all_channels.items():
            ch_col = find_column(df, ["channel", "chan", "ch"])
            type_col = find_column(df, ["type", "product", "variant", "item", "family"])
            if not ch_col or not type_col: continue

            cum_col = find_column(df, ["cumulative", "cum"])
            prod_col = find_column(df, ["production", "prod"])
            date_col = find_column(df, ["date"])

            for _, row in df.iterrows():
                channel_num = normalize_channel(row.get(ch_col))
                prod_str = row.get(type_col)
                family, _ = parse_family_and_type(prod_str)
                if not channel_num or not family: continue

                cumulative = clean_nan(row.get(cum_col)) if cum_col else 0.0
                production = clean_nan(row.get(prod_col)) if prod_col else 0.0
                date_val = parse_date_safe(row.get(date_col)) if date_col else None

                c_key = (channel_num, family)
                if c_key not in channel_data:
                    channel_data[c_key] = {"max_cum": 0.0, "in_date": None, "out_date": None}
                
                c_meta = channel_data[c_key]
                if cumulative > c_meta["max_cum"]:
                    c_meta["max_cum"] = cumulative
                
                if date_val:
                    if production > 0 and production == cumulative:
                        c_meta["in_date"] = min(c_meta["in_date"], date_val) if c_meta["in_date"] else date_val
                    c_meta["out_date"] = max(c_meta["out_date"], date_val) if c_meta["out_date"] else date_val

        # ---------------------------------------------------------
        # 2. PARSE MASTER GROUND TRUTH MO DATA MAPS
        # ---------------------------------------------------------
        mo_dict = {}
        for sheet_name, df in mo_sheets.items():
            mo_col = find_column(df, ["mo#", "mo number", "mo_num", "mo"])
            prod_col = find_column(df, ["finalvariant", "product", "variant", "type", "item"])
            qty_col = find_column(df, ["qty req", "target qty", "quantity", "qty"])
            if not mo_col or not prod_col: continue

            for _, row in df.iterrows():
                mo_num = clean_mo(row.get(mo_col))
                prod_val = row.get(prod_col)
                family, _ = parse_family_and_type(prod_val)
                target = clean_nan(row.get(qty_col)) if qty_col else 0.0
                
                if family and mo_num:
                    mo_dict[family] = {"mo": mo_num, "target": target}

        # ---------------------------------------------------------
        # 3. PROCESS RING WT TRANSIT BUFFER (THE STRUCTURAL BASE)
        # ---------------------------------------------------------
        ring_wt_aggregated = {}
        
        for sheet_name, df in ring_wt_sheets.items():
            ch_col = find_column(df, ["channel", "chan", "ch"])
            type_col = find_column(df, ["type", "product", "variant", "item", "family"])
            qty_col = find_column(df, ["qty", "quantity"])
            date_col = find_column(df, ["date", "challan"])
            
            if not ch_col or not type_col: continue
            
            for _, row in df.iterrows():
                channel_num = normalize_channel(row.get(ch_col))
                prod_str = row.get(type_col)
                family, comp_type = parse_family_and_type(prod_str)
                if not channel_num or not family: continue

                qty = clean_nan(row.get(qty_col)) if qty_col else 0.0
                date_val = parse_date_safe(row.get(date_col)) if date_col else None

                r_key = (channel_num, family, comp_type)
                if r_key not in ring_wt_aggregated:
                    ring_wt_aggregated[r_key] = {"qty": 0.0, "max_date": None}
                
                ring_wt_aggregated[r_key]["qty"] += qty
                if date_val:
                    if ring_wt_aggregated[r_key]["max_date"]:
                        ring_wt_aggregated[r_key]["max_date"] = max(ring_wt_aggregated[r_key]["max_date"], date_val)
                    else:
                        ring_wt_aggregated[r_key]["max_date"] = date_val

        # ---------------------------------------------------------
        # 4. DATA COMPILATION STAGE
        # ---------------------------------------------------------
        compiled_summary = []
        
        for (channel_num, family, comp_type), rw_data in ring_wt_aggregated.items():
            c_key = (channel_num, family)
            ch_info = channel_data.get(c_key, {"max_cum": None, "in_date": None, "out_date": None})
            mo_info = mo_dict.get(family, {"mo": "", "target": 0.0})
            
            calc_status = "In Process"
            if ch_info["max_cum"] and ch_info["max_cum"] >= rw_data["qty"] and rw_data["qty"] > 0:
                calc_status = "Completed"
            elif rw_data["qty"] == 0 and not ch_info["max_cum"]:
                calc_status = "Yet to Start"

            compiled_summary.append({
                "mo_number": mo_info["mo"],
                "product_variant": family,  # Strictly Outputs exact derived bearing family
                "target_qty": int(mo_info["target"]) if mo_info["target"] > 0 else "",
                "ring_type": comp_type,
                "sho_qty": rw_data["qty"],
                "sho_in": "",
                "tb_qty": rw_data["qty"],
                "tb_out": str(rw_data["max_date"]) if rw_data["max_date"] else "-",
                "ch_qty": int(ch_info["max_cum"]) if ch_info["max_cum"] is not None else "",
                "ch_in": str(ch_info["in_date"]) if ch_info["in_date"] else "-",
                "ch_out": str(ch_info["out_date"]) if ch_info["out_date"] else "-",
                "status": calc_status,
                "channel_ref": channel_num
            })

        # Final Sort Arrangement
        compiled_summary.sort(key=lambda x: (x["mo_number"], x["product_variant"], x["ring_type"]))
        
        MASTER_CACHE = compiled_summary
        LAST_REFRESH = datetime.now()
        print(f"[{datetime.now()}] SUCCESS: TBE MATRIX SYNCHRONIZED. ROWS PROCESSED: {len(MASTER_CACHE)}")

    except Exception as e:
        print(f"CRITICAL TRANSIT BLOCK DATA PARSER ERROR: {str(e)}")
    finally:
        IS_UPDATING = False

def background_refresh_loop():
    process_tbe_data()
    while True:
        time.sleep(CACHE_DURATION_MINUTES * 60)
        process_tbe_data()

t = threading.Thread(target=background_refresh_loop, daemon=True)
t.start()

@router.get("/tbe_all_mos")
def get_tbe_data():
    if not LAST_REFRESH and not MASTER_CACHE:
        return {
            "status": "initializing",
            "message": "System maps are being prepared. Please hold...",
            "data": []
        }
    return {
        "status": "success",
        "data": MASTER_CACHE
    }
