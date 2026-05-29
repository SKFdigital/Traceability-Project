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
# GLOBAL CACHE & THREADING CONFIG
# =========================================================
MASTER_CACHE = []
FLOW_CACHE = {}
LAST_REFRESH = None
IS_UPDATING = False
CACHE_DURATION_MINUTES = 5

# =========================================================
# CLEANING & PARSING HELPERS
# =========================================================
def clean_mo(value):
    if pd.isna(value): return None
    val = str(value).strip().upper().replace(" ", "").replace(".0", "")
    if val in ["NAN", "-", "...", ""] or len(val) < 2: return None
    return val

def get_mo_group(clean_mo_str):
    if clean_mo_str and len(clean_mo_str) >= 4: return clean_mo_str[:4]
    return clean_mo_str

def normalize_text(value):
    if pd.isna(value): return ""
    return str(value).strip().upper()

def clean_channel(value):
    if pd.isna(value): return ""
    return str(value).strip().upper().replace(" ", "")

def clean_nan(value):
    try:
        if pd.isna(value) or str(value).strip().lower() in ['nan', '-', '...', '']: return 0.0
        f_val = float(value)
        return 0.0 if math.isnan(f_val) else f_val
    except: return 0.0

def parse_date_safe(value):
    try:
        if pd.isna(value) or str(value).strip().lower() in ["nan", "nat", "", "-"]: return None
        parsed = pd.to_datetime(value, errors='coerce', dayfirst=True)
        return None if pd.isna(parsed) else parsed.date()
    except: return None

def extract_ring_type(product_text):
    text = normalize_text(product_text)
    if "IM" in text or "IR" in text: return "IM"
    return "OM"

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
            except Exception as e: print(f"Error reading sheet [{sheet}]: {str(e)}")
        return sheets
    except Exception as e:
        print(f"Failed to load workbook from {url}: {str(e)}")
        return {}

# =========================================================
# MAIN PROCESSING CORE LOGIC
# =========================================================
def process_tbe_dashboard_data():
    global MASTER_CACHE, FLOW_CACHE, LAST_REFRESH, IS_UPDATING
    if IS_UPDATING: return
    IS_UPDATING = True

    try:
        mo_sheets = load_excel_sheets(settings.MO_DATA_URL)
        transit_buffer_sheets = load_excel_sheets(settings.RINGWT_TRANSITBUFFER_URL)
        trb_sheets = load_excel_sheets(settings.TRB_MASTER_URL)
        dgbb_sheets = load_excel_sheets(settings.DGBB_MASTER_URL)

        tbe_aggregation = {}
        mo_flow_records = {}

        # RULE 1: TARGET QTY LOOKUP
        target_qty_lookup = {}
        for _, df in mo_sheets.items():
            mo_col = next((c for c in ["mo#", "mo"] if c in df.columns), None)
            qty_col = next((c for c in ["qty req", "qty", "target qty"] if c in df.columns), None)
            if not mo_col or not qty_col: continue
            for _, row in df.iterrows():
                raw_mo = clean_mo(row.get(mo_col))
                if raw_mo:
                    mo_grp = get_mo_group(raw_mo)
                    target_qty_lookup[mo_grp] = target_qty_lookup.get(mo_grp, 0.0) + clean_nan(row.get(qty_col))

        # RULE 2: ANCHOR CHANNELS
        all_channels = {**trb_sheets, **dgbb_sheets}
        for _, df in all_channels.items():
            mo_col = "mo" if "mo" in df.columns else ("mo#" if "mo#" in df.columns else None)
            type_col = next((c for c in ["type", "product", "product variant"] if c in df.columns), None)
            channel_col = next((c for c in ["channel", "ch#", "channel no"] if c in df.columns), None)
            if not mo_col or not type_col: continue

            for _, row in df.iterrows():
                raw_mo = clean_mo(row.get(mo_col))
                if not raw_mo: continue
                
                mo_group = get_mo_group(raw_mo)
                variant_raw = normalize_text(row.get(type_col))
                ring_type = extract_ring_type(variant_raw)
                channel_id = clean_channel(row.get(channel_col)) if channel_col else ""
                family_item = variant_raw.split('_')[0].split(' ')[0] if variant_raw else "Unknown Family"
                
                cum_production = clean_nan(row.get("cumulative production"))
                production = clean_nan(row.get("production"))
                row_date = parse_date_safe(row.get("date"))

                agg_key = (mo_group, family_item, ring_type)
                if agg_key not in tbe_aggregation:
                    tbe_aggregation[agg_key] = {
                        "mo_number": raw_mo, "mo_group": mo_group, "product_variant": family_item,
                        "target_qty": target_qty_lookup.get(mo_group, 0), "ring_type": ring_type,
                        "channel_id": channel_id, "sho_qty": 0.0, "sho_in_date": "-", 
                        "tb_qty": 0.0, "tb_out_date": None, "max_cumulative": 0.0,
                        "ch_in_date": None, "ch_out_date": None
                    }

                meta = tbe_aggregation[agg_key]
                if cum_production > meta["max_cumulative"]:
                    meta["max_cumulative"] = cum_production
                    if row_date: meta["ch_out_date"] = row_date

                if production > 0 and production == cum_production:
                    if row_date:
                        if meta["ch_in_date"] is None or row_date < meta["ch_in_date"]: meta["ch_in_date"] = row_date

        # RULE 3: TRANSIT BUFFER (No of Rings)
        for _, df in transit_buffer_sheets.items():
            ch_col = next((c for c in ["ch#", "channel", "ch"] if c in df.columns), None)
            type_col = "type" if "type" in df.columns else None
            qty_col = "no of rings" if "no of rings" in df.columns else None
            date_col = "date" if "date" in df.columns else None
            if not ch_col or not type_col or not qty_col: continue

            for _, row in df.iterrows():
                tb_channel = clean_channel(row.get(ch_col))
                tb_type_raw = normalize_text(row.get(type_col))
                row_ring_type = extract_ring_type(tb_type_raw)
                qty_tb = clean_nan(row.get(qty_col))
                tb_date = parse_date_safe(row.get(date_col))

                for agg_key, meta in tbe_aggregation.items():
                    if meta["channel_id"] == tb_channel and meta["ring_type"] == row_ring_type:
                        meta["tb_qty"] += qty_tb
                        if tb_date:
                            if meta["tb_out_date"] is None or tb_date > meta["tb_out_date"]: meta["tb_out_date"] = tb_date

        # COMPILE LIST
        compiled_summary = []
        for agg_key, meta in tbe_aggregation.items():
            if meta["max_cumulative"] == 0 and meta["sho_qty"] == 0: tracking_status = "Yet to Start"
            elif meta["max_cumulative"] >= meta["sho_qty"] and meta["sho_qty"] > 0: tracking_status = "Completed"
            else: tracking_status = "In Process"

            compiled_summary.append({
                "mo_number": meta["mo_number"],
                "product_variant": meta["product_variant"],
                "target_qty": int(meta["target_qty"]) if meta["target_qty"] > 0 else "-",
                "ring_type": meta["ring_type"],
                "sho_qty": meta["sho_qty"] if meta["sho_qty"] > 0 else meta["max_cumulative"],
                "sho_in_date": "-", 
                "tb_qty": meta["tb_qty"] if meta["tb_qty"] > 0 else meta["max_cumulative"],
                "tb_out_date": str(meta["tb_out_date"]) if meta["tb_out_date"] else "-",
                "ch_qty": meta["max_cumulative"],
                "ch_in_date": str(meta["ch_in_date"]) if meta["ch_in_date"] else "-",
                "ch_out_date": str(meta["ch_out_date"]) if meta["ch_out_date"] else "-",
                "tracking_status": tracking_status
            })

            m_group = meta["mo_group"]
            if m_group not in mo_flow_records: mo_flow_records[m_group] = {"mo": meta["mo_number"], "timeline": []}
            mo_flow_records[m_group]["timeline"].append(compiled_summary[-1])

        compiled_summary.sort(key=lambda x: (x["mo_number"], x["product_variant"]))
        
        MASTER_CACHE = compiled_summary
        FLOW_CACHE = mo_flow_records
        LAST_REFRESH = datetime.now()

    except Exception as e: print(f"CRITICAL ERROR: {str(e)}")
    finally: IS_UPDATING = False

def background_refresh_loop():
    process_tbe_dashboard_data()
    while True:
        time.sleep(CACHE_DURATION_MINUTES * 60)
        process_tbe_dashboard_data()

t = threading.Thread(target=background_refresh_loop, daemon=True)
t.start()

# RESTORED OLD ENDPOINT NAMES TO FIX FRONTEND NETWORK ERROR
@router.get("/traceability_all_mos")
def get_all_mos():
    if not LAST_REFRESH and not MASTER_CACHE:
        return {"status": "initializing", "message": "Loading...", "data": []}
    return {"status": "success", "last_updated": str(LAST_REFRESH), "data": MASTER_CACHE}

@router.get("/traceability_report/{mo}")
def get_flow(mo: str):
    search_mo = get_mo_group(clean_mo(mo))
    if search_mo in FLOW_CACHE:
        return {"status": "success", "last_updated": str(LAST_REFRESH), "data": FLOW_CACHE[search_mo]}
    raise HTTPException(status_code=404, detail=f"Not found: '{mo}'")
