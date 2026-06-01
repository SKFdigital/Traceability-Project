from fastapi import APIRouter
import pandas as pd
import requests
import io
import threading
import time
import math
from datetime import datetime

router = APIRouter()

# =========================================================
# GLOBAL CACHE & INITIALIZATION MONITOR
# =========================================================
MASTER_CACHE = []
LAST_REFRESH = None
IS_UPDATING = False
INITIALIZED = False  
CACHE_DURATION_MINUTES = 5

# =========================================================
# ADVANCED RESILIENT HELPERS
# =========================================================
def repair_sheet_headers(df):
    if df.empty:
        return df
    
    targets = {"mo", "ch", "type", "qty", "quantity", "rings", "date", "channel", "production", "weight", "item", "line"}
    
    current_cols = [str(c).strip().lower().replace(" ", "") for c in df.columns]
    if sum(1 for t in targets if any(t in c for c in current_cols)) >= 2:
        if not any("unnamed:" in str(c).lower() for c in df.columns[:2]):
            return df
            
    for idx in range(min(10, len(df))):
        row_vals = [str(val).strip().lower().replace(" ", "") for val in df.iloc[idx].dropna()]
        match_count = sum(1 for t in targets if any(t in v for v in row_vals))
        
        if match_count >= 2:
            new_cols = df.iloc[idx].tolist()
            new_cols = [str(c).strip() if pd.notna(c) else f"Unnamed_{i}" for i, c in enumerate(new_cols)]
            repaired_df = df.iloc[idx+1:].copy()
            repaired_df.columns = new_cols
            return repaired_df.reset_index(drop=True)
            
    return df

def normalize_channel(value):
    if pd.isna(value): 
        return ""
    val_str = str(value).strip().upper()
    for prefix in ["CH-", "CH.", "CH", "CHANNEL-", "CHANNEL", "T-", "T", "SHEET", "SHEET-"]:
        if val_str.startswith(prefix):
            val_str = val_str[len(prefix):].strip()
    val_str = val_str.replace("-", "").replace(" ", "").strip()
    if val_str.endswith(".0"): 
        val_str = val_str[:-2]
    cleaned = val_str.lstrip("0")
    return cleaned if cleaned else "0"

def parse_family_and_type(prod_text):
    text = str(prod_text).strip().upper()
    if not text or text in ["NAN", "NONE", ""]: 
        return "UNKNOWN", "Assembly"
    
    r_type = "IM" if any(x in text for x in ["IM", "IR"]) else ("OM" if any(x in text for x in ["OM", "OR"]) else "Assembly")
    
    clean = text
    prefixes = ["IM-", "OM-", "IR-", "OR-", "IM", "OM", "TRB-", "DGBB-", "CH-"]
    for p in prefixes:
        if clean.startswith(p): 
            clean = clean[len(p):]
    suffixes = ["-IM", "-OM", "-IR", "-OR"]
    for s in suffixes:
        if clean.endswith(s): 
            clean = clean[:-len(s)]
            
    return clean.strip(" -_"), r_type

def find_column(df, patterns):
    cols_map = {str(c).strip().lower().replace(" ", "").replace("#", "").replace("_", ""): c for c in df.columns}
    for pattern in patterns:
        norm_p = pattern.lower().replace(" ", "").replace("#", "").replace("_", "")
        if norm_p in cols_map:
            return cols_map[norm_p]
        for normalized_target, original_col in cols_map.items():
            if norm_p in normalized_target or normalized_target in norm_p:
                return original_col
    return None

def clean_nan(value):
    try:
        if pd.isna(value) or str(value).strip().lower() in ['nan', '-', '...', '']:
            return 0.0
        f_val = float(value)
        return 0.0 if math.isnan(f_val) else f_val
    except:
        return 0.0

def parse_date_safe(value):
    try:
        if pd.isna(value) or str(value).strip().lower() in ["nan", "nat", "", "-", "none"]:
            return None
        ts = pd.to_datetime(value, dayfirst=True, errors='coerce')
        if ts is pd.NaT or pd.isna(ts):
            return None
        return ts.date()
    except:
        return None

def load_excel_sheets(url):
    try:
        from settings import settings
        resp = requests.get(url, timeout=30)
        if resp.status_code != 200: 
            return {}
        xls = pd.ExcelFile(io.BytesIO(resp.content))
        return {sheet: repair_sheet_headers(xls.parse(sheet)) for sheet in xls.sheet_names}
    except Exception as e:
        print(f"⚠️ Sheet stream down on URL: {str(e)}")
        return {}

# =========================================================
# CORE BACKGROUND DATA REFRESH LOGIC
# =========================================================
def process_tbe_data():
    global MASTER_CACHE, LAST_REFRESH, IS_UPDATING, INITIALIZED
    if IS_UPDATING: 
        return
    
    IS_UPDATING = True
    print(f"🔄 [{datetime.now().strftime('%H:%M:%S')}] Running Flat Row TBE Pipeline...")

    try:
        from settings import settings
        ring_wt_sheets = load_excel_sheets(settings.RINGWT_TRANSITBUFFER_URL)
        channel_master_sheets = {**load_excel_sheets(settings.TRB_MASTER_URL), **load_excel_sheets(settings.DGBB_MASTER_URL)}

        # ---------------------------------------------------------
        # STEP 1: PARSE CHANNEL MASTER INCREMENTAL RECORDS
        # ---------------------------------------------------------
        channel_production_records = []
        
        for sheet_name, df in channel_master_sheets.items():
            if df.empty or sheet_name in ['Pivot Table 1', 'Pivot Table 2', 'PIC List', 'List']: 
                continue
            
            c_col = find_column(df, ["ch", "channel", "channelno", "channelnum", "chref", "machineno", "line", "mo"])
            type_col = find_column(df, ["type", "variant", "bearing", "product", "item", "itemdescription", "desc", "family"])
            d_col = find_column(df, ["date", "day", "txndate", "timestamp"])
            
            prod_col = find_column(df, ["production", "prodqty", "shiftproduction"])
            if not prod_col:
                prod_col = find_column(df, ["qty", "cumulative", "cum"])

            if not type_col or not prod_col: 
                continue

            for _, row in df.iterrows():
                ch = normalize_channel(row.get(c_col)) if c_col else normalize_channel(sheet_name)
                if not ch or ch == "0": 
                    continue
                
                prod_str = str(row.get(type_col)).strip().upper()
                if prod_str in ["", "NAN"]: 
                    continue
                
                base_family, _ = parse_family_and_type(prod_str)
                prod_qty = clean_nan(row.get(prod_col))
                date_val = parse_date_safe(row.get(d_col))

                if prod_qty > 0 and date_val:
                    channel_production_records.append({
                        "ch": ch, "fam": base_family, "qty": prod_qty, "date": date_val
                    })

        df_ch_prod = pd.DataFrame(channel_production_records)

        # ---------------------------------------------------------
        # STEP 2: PARSE TRANSIT BUFFER RECORDS (KEEP ALL ROWS FLAT)
        # ---------------------------------------------------------
        raw_ring_data = []
        for sheet_name, df in ring_wt_sheets.items():
            if df.empty: 
                continue
            
            c_col = find_column(df, ["ch", "channel", "channelno", "channelnum", "chref", "machineno", "mo", "line"])
            f_col = find_column(df, ["type", "variant", "product", "item", "itemdescription", "desc", "family", "part"])
            q_col = find_column(df, ["noofrings", "quantity", "qty", "rings", "totalqtyrecd", "recdqty", "production", "total"])
            d_col = find_column(df, ["date", "day", "txndate", "timestamp"])

            if not f_col or not q_col: 
                continue

            for _, row in df.iterrows():
                ch = normalize_channel(row.get(c_col)) if c_col else normalize_channel(sheet_name)
                if not ch or ch == "0": 
                    continue
                
                prod_text = str(row.get(f_col)).strip().upper()
                if prod_text in ["", "NAN"]: 
                    continue
                
                base_family, r_type = parse_family_and_type(prod_text)
                qty = clean_nan(row.get(q_col))
                dt = parse_date_safe(row.get(d_col))

                if qty > 0 and dt:
                    raw_ring_data.append({"ch": ch, "fam": base_family, "type": r_type, "qty": qty, "date": dt})

        df_rings = pd.DataFrame(raw_ring_data)
        if df_rings.empty:
            print("⚠️ Pipeline Warning: No records found in Transit Buffer.")
            MASTER_CACHE = []
            LAST_REFRESH = datetime.now()
            return

        # ---------------------------------------------------------
        # STEP 3: MAP PRODUCTION DIRECTLY TO EACH TRANSIT BUFFER ROW
        # ---------------------------------------------------------
        compiled_summary = []
        
        for _, row in df_rings.iterrows():
            ch = row["ch"]
            fam = row["fam"]
            r_type = row["type"]
            tb_qty = row["qty"]
            dt = row["date"]
            
            ch_qty = 0.0
            ch_min_date = None
            ch_max_date = None
            
            # Look for production matches on the same channel, variant, and exact date
            if not df_ch_prod.empty:
                mask = (df_ch_prod["ch"] == ch) & (df_ch_prod["fam"] == fam) & (df_ch_prod["date"] == dt)
                matched_prod = df_ch_prod[mask]
                
                if not matched_prod.empty:
                    ch_qty = matched_prod["qty"].sum()
                    ch_min_date = matched_prod["date"].min()
                    ch_max_date = matched_prod["date"].max()

            if tb_qty == 0 and ch_qty == 0:
                calc_status = "Yet to Start"
            elif ch_qty >= tb_qty and tb_qty > 0:
                calc_status = "Completed"
            else:
                calc_status = "In Process"

            compiled_summary.append({
                "channel_ref": ch,
                "product_variant": fam,
                "ring_type": r_type,
                "sho_qty": tb_qty, 
                "sho_in": str(dt) if dt else "-",
                "tb_qty": tb_qty,
                "tb_out": str(dt) if dt else "-",
                "ch_qty": ch_qty,
                "ch_in": str(ch_min_date) if ch_min_date else "-",
                "ch_out": str(ch_max_date) if ch_max_date else "-",
                "status": calc_status
            })

        # Keep everything neatly sorted by channel, item variant, and chronological date
        compiled_summary.sort(key=lambda x: (x["channel_ref"], x["product_variant"], x["ring_type"], x["sho_in"]))
        MASTER_CACHE = compiled_summary
        LAST_REFRESH = datetime.now()
        print(f"✅ [Engine Complete] Successfully processed {len(MASTER_CACHE)} un-grouped flat rows.")

    except Exception as e:
        print(f"❌ CRITICAL RUNTIME EXCEPTION IN LIVE AGGREGATION: {str(e)}")
    finally:
        INITIALIZED = True 
        IS_UPDATING = False

def background_refresh_loop():
    process_tbe_data()
    while True:
        time.sleep(CACHE_DURATION_MINUTES * 60)
        process_tbe_data()

threading.Thread(target=background_refresh_loop, daemon=True).start()

# =========================================================
# ROUTER SERVICE ENTRANCE
# =========================================================
@router.get("/tbe_all_mos")
def get_tbe_dashboard():
    if not INITIALIZED:
        return {
            "status": "initializing",
            "message": "Downloading and formatting remote pipeline sheets. Please wait...",
            "data": []
        }
    return {
        "status": "success",
        "last_updated": str(LAST_REFRESH),
        "data": MASTER_CACHE
    }
