from fastapi import APIRouter
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
# GLOBAL CACHE & INITIALIZATION MONITOR
# =========================================================
MASTER_CACHE = []
LAST_REFRESH = None
IS_UPDATING = False
INITIALIZED = False  # Hard guard to prevent infinite loading screens
CACHE_DURATION_MINUTES = 5

# =========================================================
# ADVANCED RESILIENT HELPERS
# =========================================================
def repair_sheet_headers(df):
    """
    Self-healing routine. Scans the top rows of a sheet to find where the true 
    production metrics headers sit, bypassing administrative banners or titles.
    """
    if df.empty:
        return df
    
    # Structural column markers to look for
    targets = {"ch", "channel", "type", "variant", "product", "item", "qty", "quantity", "rings", "date", "mo", "production"}
    
    # Test if current headers are already completely valid
    current_cols = [str(c).strip().lower().replace(" ", "") for c in df.columns]
    if sum(1 for t in targets if any(t in c for c in current_cols)) >= 2:
        if not any("unnamed:" in str(c).lower() for c in df.columns[:2]):
            return df
            
    # Scan the first 10 rows to locate where the true data matrix table begins
    for idx in range(min(10, len(df))):
        row_vals = [str(val).strip().lower().replace(" ", "") for val in df.iloc[idx].dropna()]
        match_count = sum(1 for t in targets if any(t in v for v in row_vals))
        
        if match_count >= 2:
            new_cols = df.iloc[idx].tolist()
            new_cols = [str(c).strip() if pd.notna(c) else f"Unnamed_{i}" for i, c in enumerate(new_cols)]
            repaired_df = df.iloc[idx+1:].copy()
            repaired_df.columns = new_cols
            print(f"🎯 Repaired sheet matrix structure at row index {idx}. Columns: {new_cols[:5]}")
            return repaired_df.reset_index(drop=True)
            
    return df

def normalize_channel(value):
    if pd.isna(value): 
        return ""
    val_str = str(value).strip().upper()
    for prefix in ["CH-", "CH.", "CH", "CHANNEL-", "CHANNEL"]:
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
        
        # Explicit check to stop NaT from leaking out as an object
        ts = pd.to_datetime(value, dayfirst=True, errors='coerce')
        if ts is pd.NaT or pd.isna(ts):
            return None
            
        return ts.date()
    except:
        return None

def load_excel_sheets(url):
    try:
        resp = requests.get(url, timeout=30)
        if resp.status_code != 200: 
            return {}
        xls = pd.ExcelFile(io.BytesIO(resp.content))
        return {sheet: repair_sheet_headers(xls.parse(sheet)) for sheet in xls.sheet_names}
    except Exception as e:
        print(f"⚠️ Sheet stream down on URL {url}: {str(e)}")
        return {}

# =========================================================
# CORE BACKGROUND DATA REFRESH LOGIC
# =========================================================
def process_tbe_data():
    global MASTER_CACHE, LAST_REFRESH, IS_UPDATING, INITIALIZED
    if IS_UPDATING: 
        return
    
    IS_UPDATING = True
    print(f"🔄 [{datetime.now().strftime('%H:%M:%S')}] Executing Live TBE Pipeline Data Refresh...")

    try:
        ring_wt_sheets = load_excel_sheets(settings.RINGWT_TRANSITBUFFER_URL)
        channel_master_sheets = {**load_excel_sheets(settings.TRB_MASTER_URL), **load_excel_sheets(settings.DGBB_MASTER_URL)}

        # ---------------------------------------------------------
        # STEP 1: COMPUTE CHANNEL QUALITIES (Max_Cum Targets)
        # ---------------------------------------------------------
        channel_variant_maxes = {}
        
        for sheet_name, df in channel_master_sheets.items():
            if df.empty: 
                continue
            
            c_col = find_column(df, ["ch", "channel", "channelno", "channelnum", "chref", "machineno", "line", "mo"])
            type_col = find_column(df, ["type", "variant", "bearing", "product", "item", "itemdescription", "desc", "family"])
            cum_col = find_column(df, ["cumulative", "cum", "totalproduction", "prodqty", "cumulativeproduction", "totalqty", "total"])
            d_col = find_column(df, ["date", "day", "txndate", "timestamp"])

            if not type_col or not cum_col: 
                continue

            for _, row in df.iterrows():
                ch = normalize_channel(row.get(c_col)) if c_col else normalize_channel(sheet_name)
                if not ch: 
                    continue
                
                prod_str = str(row.get(type_col)).strip().upper()
                if prod_str in ["", "NAN"]: 
                    continue
                
                base_family, _ = parse_family_and_type(prod_str)
                cumulative = clean_nan(row.get(cum_col))
                date_val = parse_date_safe(row.get(d_col))

                v_key = (ch, base_family, prod_str)
                if v_key not in channel_variant_maxes:
                    channel_variant_maxes[v_key] = {"max_cum": 0.0, "min_date": None, "max_date": None}
                
                v_meta = channel_variant_maxes[v_key]
                if cumulative > v_meta["max_cum"]:
                    v_meta["max_cum"] = cumulative
                if date_val:
                    v_meta["min_date"] = min(v_meta["min_date"], date_val) if v_meta["min_date"] else date_val
                    v_meta["max_date"] = max(v_meta["max_date"], date_val) if v_meta["max_date"] else date_val

        # Roll sub-variants into family level totals linked by Channel Code
        family_channel_totals = {}
        for (ch, base_family, prod_str), v_meta in channel_variant_maxes.items():
            f_key = (ch, base_family)
            if f_key not in family_channel_totals:
                family_channel_totals[f_key] = {"ch_qty": 0.0, "ch_in_date": None, "ch_out_date": None}
            
            f_meta = family_channel_totals[f_key]
            f_meta["ch_qty"] += v_meta["max_cum"]
            if v_meta["min_date"]:
                f_meta["ch_in_date"] = min(f_meta["ch_in_date"], v_meta["min_date"]) if f_meta["ch_in_date"] else v_meta["min_date"]
            if v_meta["max_date"]:
                f_meta["ch_out_date"] = max(f_meta["ch_out_date"], v_meta["max_date"]) if f_meta["ch_out_date"] else v_meta["max_date"]

        # ---------------------------------------------------------
        # STEP 2: PARSE TRANSIT BUFFER RING SPREADSHEETS
        # ---------------------------------------------------------
        raw_ring_data = []
        for sheet_name, df in ring_wt_sheets.items():
            if df.empty: 
                continue
            
            c_col = find_column(df, ["ch", "channel", "channelno", "channelnum", "chref", "machineno", "mo"])
            f_col = find_column(df, ["type", "variant", "product", "item", "itemdescription", "desc", "family"])
            q_col = find_column(df, ["noofrings", "quantity", "qty", "rings", "totalqtyrecd", "recdqty", "production"])
            d_col = find_column(df, ["date", "day", "txndate", "timestamp"])

            if not f_col or not q_col: 
                continue

            for _, row in df.iterrows():
                ch = normalize_channel(row.get(c_col)) if c_col else normalize_channel(sheet_name)
                if not ch: 
                    continue
                
                prod_text = str(row.get(f_col)).strip().upper()
                if prod_text in ["", "NAN"]: 
                    continue
                
                base_family, r_type = parse_family_and_type(prod_text)
                qty = clean_nan(row.get(q_col))
                
                dt = parse_date_safe(row.get(d_col))
                if dt is None:
                    dt = datetime.now().date()

                if qty > 0:
                    raw_ring_data.append({"ch": ch, "fam": base_family, "type": r_type, "qty": qty, "date": dt})

        df_rings = pd.DataFrame(raw_ring_data)
        if df_rings.empty:
            print("⚠️ Pipeline Warning: No actionable component rows extracted. Clearing cached data.")
            MASTER_CACHE = []
            LAST_REFRESH = datetime.now()
            return

        # ---------------------------------------------------------
        # STEP 3: CONSOLIDATE DATA VIA 7-DAY WAVE SCHEDULING
        # ---------------------------------------------------------
        df_rings = df_rings.sort_values(by=['ch', 'fam', 'type', 'date'])
        compiled_summary = []

        for (ch, fam, r_type), group in df_rings.groupby(['ch', 'fam', 'type']):
            current_batch_qty = 0.0
            batch_start = None
            last_date = None

            for _, row in group.iterrows():
                if last_date is None or (row['date'] - last_date).days <= 7:
                    current_batch_qty += row['qty']
                    if batch_start is None: 
                        batch_start = row['date']
                    last_date = row['date']
                else:
                    compiled_summary.append(build_matrix_row(ch, fam, r_type, current_batch_qty, last_date, family_channel_totals))
                    current_batch_qty = row['qty']
                    batch_start = row['date']
                    last_date = row['date']
            
            if batch_start is not None:
                compiled_summary.append(build_matrix_row(ch, fam, r_type, current_batch_qty, last_date, family_channel_totals))

        compiled_summary.sort(key=lambda x: (x["channel_ref"], x["product_variant"], x["ring_type"]))
        MASTER_CACHE = compiled_summary
        LAST_REFRESH = datetime.now()
        print(f"✅ [TBE Pipeline Engine Complete] Successfully structured {len(MASTER_CACHE)} logistics matrix records.")

    except Exception as e:
        print(f"❌ CRITICAL RUNTIME EXCEPTION IN BACKGROUND PROCESSING THREAD: {str(e)}")
    finally:
        INITIALIZED = True 
        IS_UPDATING = False

def build_matrix_row(ch, fam, r_type, total_ring_qty, final_date, family_channel_totals):
    chan_link = family_channel_totals.get((ch, fam), {"ch_qty": 0.0, "ch_in_date": None, "ch_out_date": None})
    ch_qty = chan_link["ch_qty"]

    if total_ring_qty == 0 and ch_qty == 0:
        calc_status = "Yet to Start"
    elif ch_qty >= total_ring_qty and total_ring_qty > 0:
        calc_status = "Completed"
    else:
        calc_status = "In Process"

    return {
        "channel_ref": ch,
        "product_variant": fam,
        "ring_type": r_type,
        "sho_qty": total_ring_qty,
        "sho_in": "-",
        "tb_qty": total_ring_qty,
        "tb_out": str(final_date) if final_date else "-",
        "ch_qty": ch_qty,
        "ch_in": str(chan_link["ch_in_date"]) if chan_link["ch_in_date"] else "-",
        "ch_out": str(chan_link["ch_out_date"]) if chan_link["ch_out_date"] else "-",
        "status": calc_status
    }

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
