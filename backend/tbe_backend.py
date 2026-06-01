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
# RESILIENT HELPERS
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

def find_column(df, patterns):
    cols = [str(c).strip() for c in df.columns]
    
    # Pass 1: Strict Exact Case-Insensitive Match
    for p in patterns:
        norm_p = p.lower().replace(" ", "").replace("_", "").replace("#", "")
        for c in cols:
            norm_c = c.lower().replace(" ", "").replace("_", "").replace("#", "")
            if norm_c == norm_p:
                return c
                
    # Pass 2: Substring Match (Disabled for short tokens like 'ch'/'mo' to prevent hijacking)
    for p in patterns:
        norm_p = p.lower().replace(" ", "").replace("_", "")
        if len(norm_p) <= 2: 
            continue
        for c in cols:
            norm_c = c.lower().replace(" ", "").replace("_", "")
            if norm_p in norm_c or norm_c in norm_p:
                return c
    return None

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
        print(f"⚠️ Sheet stream down: {str(e)}")
        return {}

# =========================================================
# CORE AGGREGATION ENGINE (PURE VARIANT GROUPING)
# =========================================================
def process_tbe_data():
    global MASTER_CACHE, LAST_REFRESH, IS_UPDATING, INITIALIZED
    if IS_UPDATING: 
        return
    
    IS_UPDATING = True
    print(f"🔄 [{datetime.now().strftime('%H:%M:%S')}] Processing Clean Variant Aggregation Pipeline...")

    try:
        from settings import settings
        ring_wt_sheets = load_excel_sheets(settings.RINGWT_TRANSITBUFFER_URL)
        channel_master_sheets = {**load_excel_sheets(settings.TRB_MASTER_URL), **load_excel_sheets(settings.DGBB_MASTER_URL)}

        # ---------------------------------------------------------
        # STEP 1: EXTRACT & GROUP ALL CHANNEL PRODUCTION RECORDS
        # ---------------------------------------------------------
        ch_list = []
        for sheet_name, df in channel_master_sheets.items():
            if df.empty or sheet_name in ['Pivot Table 1', 'Pivot Table 2', 'PIC List', 'List']: 
                continue
            
            c_col = find_column(df, ["channel", "channelno", "channelnum", "chref", "machineno", "line", "mo", "ch"])
            type_col = find_column(df, ["type", "variant", "bearing", "product", "item", "itemdescription", "desc", "family"])
            d_col = find_column(df, ["date", "day", "txndate", "timestamp"])
            prod_col = find_column(df, ["production", "prodqty", "shiftproduction", "qty", "cumulative"])

            if not type_col or not prod_col: 
                continue

            for _, row in df.iterrows():
                ch = normalize_channel(row.get(c_col)) if c_col else normalize_channel(sheet_name)
                if not ch or ch == "0": 
                    ch = normalize_channel(sheet_name)
                
                prod_str = str(row.get(type_col)).strip().upper()
                if prod_str in ["", "NAN"]: 
                    continue
                
                base_family, r_type = parse_family_and_type(prod_str)
                qty = clean_nan(row.get(prod_col))
                dt = parse_date_safe(row.get(d_col))

                if qty > 0:  # Kept regardless of date formatting status
                    ch_list.append({"ch": ch, "fam": base_family, "type": r_type, "qty": qty, "date": dt})

        if ch_list:
            df_ch_raw = pd.DataFrame(ch_list)
            df_ch_grouped = df_ch_raw.groupby(["ch", "fam", "type"]).agg(
                ch_qty=('qty', 'sum'),
                ch_min_date=('date', lambda x: min([d for d in x if d is not None], default=None)),
                ch_max_date=('date', lambda x: max([d for d in x if d is not None], default=None))
            ).reset_index()
        else:
            df_ch_grouped = pd.DataFrame(columns=["ch", "fam", "type", "ch_qty", "ch_min_date", "ch_max_date"])

        # ---------------------------------------------------------
        # STEP 2: EXTRACT & GROUP ALL TRANSIT BUFFER RECORDS
        # ---------------------------------------------------------
        tb_list = []
        for sheet_name, df in ring_wt_sheets.items():
            if df.empty: 
                continue
            
            c_col = find_column(df, ["channelref", "channel", "channelno", "channelnum", "machineno", "mo", "line", "ch"])
            f_col = find_column(df, ["ringfamily", "family", "type", "variant", "product", "item", "itemdescription", "desc", "part"])
            q_col = find_column(df, ["qty", "quantity", "noofrings", "rings", "totalqtyrecd", "recdqty"])
            d_col = find_column(df, ["date", "indate", "outdate", "day", "txndate"])

            if not f_col or not q_col: 
                continue

            for _, row in df.iterrows():
                ch = normalize_channel(row.get(c_col)) if c_col else normalize_channel(sheet_name)
                if not ch or ch == "0": 
                    ch = normalize_channel(sheet_name)
                
                prod_text = str(row.get(f_col)).strip().upper()
                if prod_text in ["", "NAN"]: 
                    continue
                
                base_family, r_type = parse_family_and_type(prod_text)
                qty = clean_nan(row.get(q_col))
                dt = parse_date_safe(row.get(d_col))

                if qty > 0:  # Kept regardless of date formatting status
                    tb_list.append({"ch": ch, "fam": base_family, "type": r_type, "qty": qty, "date": dt})

        if tb_list:
            df_tb_raw = pd.DataFrame(tb_list)
            df_tb_grouped = df_tb_raw.groupby(["ch", "fam", "type"]).agg(
                tb_qty=('qty', 'sum'),
                tb_min_date=('date', lambda x: min([d for d in x if d is not None], default=None)),
                tb_max_date=('date', lambda x: max([d for d in x if d is not None], default=None))
            ).reset_index()
        else:
            df_tb_grouped = pd.DataFrame(columns=["ch", "fam", "type", "tb_qty", "tb_min_date", "tb_max_date"])

        # ---------------------------------------------------------
        # STEP 3: PURE FULL OUTER JOIN BY VARIANT ON THE CHANNEL
        # ---------------------------------------------------------
        if df_tb_grouped.empty and df_ch_grouped.empty:
            MASTER_CACHE = []
            LAST_REFRESH = datetime.now()
            return

        merged = pd.merge(df_tb_grouped, df_ch_grouped, on=["ch", "fam", "type"], how="outer")
        
        compiled_summary = []
        for _, row in merged.iterrows():
            ch = row["ch"]
            fam = row["fam"]
            r_type = row["type"]
            
            tb_qty = clean_nan(row.get("tb_qty"))
            ch_qty = clean_nan(row.get("ch_qty"))
            
            tb_min = row.get("tb_min_date")
            tb_max = row.get("tb_max_date")
            ch_min = row.get("ch_min_date")
            ch_max = row.get("ch_max_date")

            # Determine statuses based strictly on grouped metrics
            if tb_qty == 0 and ch_qty > 0:
                calc_status = "Channel Only"
            elif tb_qty > 0 and ch_qty == 0:
                calc_status = "Yet to Start"
            elif ch_qty >= tb_qty:
                calc_status = "Completed"
            else:
                calc_status = "In Process"

            compiled_summary.append({
                "channel_ref": ch,
                "product_variant": fam,
                "ring_type": r_type,
                "sho_qty": tb_qty, 
                "sho_in": str(tb_min) if pd.notna(tb_min) and tb_min else "-",
                "tb_qty": tb_qty,
                "tb_out": str(tb_max) if pd.notna(tb_max) and tb_max else "-",
                "ch_qty": ch_qty,
                "ch_in": str(ch_min) if pd.notna(ch_min) and ch_min else "-",
                "ch_out": str(ch_max) if pd.notna(ch_max) and ch_max else "-",
                "status": calc_status
            })

        # Sort cleanly by channel and product family
        compiled_summary.sort(key=lambda x: (x["channel_ref"], x["product_variant"], x["ring_type"]))
        
        MASTER_CACHE = compiled_summary
        LAST_REFRESH = datetime.now()
        print(f"✅ [Engine Complete] Clean Outer-Join Aggregation complete. Total Groups: {len(MASTER_CACHE)}")

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
