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
# GLOBAL CACHE CONFIG
# =========================================================
MASTER_CACHE = []
LAST_REFRESH = None
IS_UPDATING = False
CACHE_DURATION_MINUTES = 5

# =========================================================
# CLEANING & PARSING HELPERS (Defensive Engineering)
# =========================================================
def normalize_channel(value):
    if pd.isna(value): return ""
    val_str = str(value).strip().upper()
    val_str = val_str.replace("CH-", "").replace("CH", "").replace("-", "").strip()
    if val_str.endswith(".0"): val_str = val_str[:-2]
    return val_str.lstrip("0") if val_str.lstrip("0") else "0"

def parse_family_and_type(prod_text):
    text = str(prod_text).strip().upper()
    if not text or text == "NAN": return "UNKNOWN", "Assembly"
    
    # Determine ring component type
    r_type = "IM" if any(x in text for x in ["IM", "IR"]) else ("OM" if any(x in text for x in ["OM", "OR"]) else "Assembly")
    
    # Extract clean base family by removing structural prefixes/suffixes
    clean = text
    for p in ["IM-", "OM-", "IR-", "OR-", "IM", "OM", "TRB-", "DGBB-"]:
        if clean.startswith(p): clean = clean[len(p):]
    for s in ["-IM", "-OM", "-IR", "-OR"]:
        if clean.endswith(s): clean = clean[:-len(s)]
        
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
        if pd.isna(value) or str(value).strip().lower() in ["nan", "nat", "", "-"]:
            return None
        return pd.to_datetime(value, dayfirst=True, errors='coerce').date()
    except:
        return None

def find_column(df, patterns):
    for pattern in patterns:
        for col in df.columns:
            if pattern in str(col).strip().lower():
                return col
    return None

def load_excel_sheets(url):
    try:
        resp = requests.get(url, timeout=30)
        if resp.status_code != 200: return {}
        xls = pd.ExcelFile(io.BytesIO(resp.content))
        sheets = {}
        for s in xls.sheet_names:
            df = xls.parse(s)
            df.columns = [str(c).lower().strip() for c in df.columns]
            sheets[s] = df
        return sheets
    except:
        return {}

# =========================================================
# CORE PROCESSING ENGINE
# =========================================================
def process_tbe_data():
    global MASTER_CACHE, LAST_REFRESH, IS_UPDATING
    if IS_UPDATING: return
    
    IS_UPDATING = True
    print(f"🔄 [{datetime.now().strftime('%H:%M:%S')}] starting TBE Data pipeline calculation...")

    try:
        # Load sheets from source URL streams
        ring_wt_sheets = load_excel_sheets(settings.RINGWT_TRANSITBUFFER_URL)
        channel_master_sheets = {**load_excel_sheets(settings.TRB_MASTER_URL), **load_excel_sheets(settings.DGBB_MASTER_URL)}

        # ---------------------------------------------------------
        # STEP 1: DERIVE CHANNEL QUANTITIES (Replicated Reference Logic)
        # ---------------------------------------------------------
        channel_variant_maxes = {}
        
        for sheet_name, df in channel_master_sheets.items():
            c_col = find_column(df, ["ch#", "channel"])
            type_col = find_column(df, ["type", "variant", "bearing", "product"])
            cum_col = find_column(df, ["cumulative production", "cumulative", "cum"])
            d_col = find_column(df, ["date"])

            if not c_col or not type_col or not cum_col:
                continue

            for _, row in df.iterrows():
                ch = normalize_channel(row.get(c_col))
                if not ch: continue
                
                prod_str = str(row.get(type_col)).strip().upper()
                base_family, _ = parse_family_and_type(prod_str)
                cumulative = clean_nan(row.get(cum_col))
                date_val = parse_date_safe(row.get(d_col))

                # Unique tracker path to isolate specific item sub-variants
                v_key = (ch, base_family, prod_str)
                if v_key not in channel_variant_maxes:
                    channel_variant_maxes[v_key] = {"max_cum": 0.0, "min_date": None, "max_date": None}
                
                v_meta = channel_variant_maxes[v_key]
                if cumulative > v_meta["max_cum"]:
                    v_meta["max_cum"] = cumulative
                if date_val:
                    v_meta["min_date"] = min(v_meta["min_date"], date_val) if v_meta["min_date"] else date_val
                    v_meta["max_date"] = max(v_meta["max_date"], date_val) if v_meta["max_date"] else date_val

        # Roll up sub-variants to Family level grouped under the unique Channel Number
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
        # STEP 2: PROCESS RINGWT_TRANSITBUFFER SPREADSHEET
        # ---------------------------------------------------------
        raw_ring_data = []
        for sheet_name, df in ring_wt_sheets.items():
            c_col = find_column(df, ["ch#", "channel"])
            f_col = find_column(df, ["type", "variant", "product"])
            q_col = find_column(df, ["no of rings", "quantity", "qty"]) # Primary extraction target
            d_col = find_column(df, ["date"])

            if not c_col or not f_col or not q_col:
                continue

            for _, row in df.iterrows():
                ch = normalize_channel(row.get(c_col))
                if not ch: continue
                
                prod_text = str(row.get(f_col)).strip().upper()
                base_family, r_type = parse_family_and_type(prod_text)
                qty = clean_nan(row.get(q_col))
                dt = parse_date_safe(row.get(d_col)) or datetime.now().date()

                if qty > 0:
                    raw_ring_data.append({"ch": ch, "fam": base_family, "type": r_type, "qty": qty, "date": dt})

        df_rings = pd.DataFrame(raw_ring_data)
        if df_rings.empty:
            MASTER_CACHE = []
            return

        # ---------------------------------------------------------
        # STEP 3: APPLY 7-DAY WAVE SEQUENCING MATRIX
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
                    if batch_start is None: batch_start = row['date']
                    last_date = row['date']
                else:
                    # Emit previous batch total before resetting
                    compiled_summary.append(build_matrix_row(ch, fam, r_type, current_batch_qty, last_date, family_channel_totals))
                    current_batch_qty = row['qty']
                    batch_start = row['date']
                    last_date = row['date']
            
            # Close out lagging open sequence loop
            if batch_start is not None:
                compiled_summary.append(build_matrix_row(ch, fam, r_type, current_batch_qty, last_date, family_channel_totals))

        # Sort matrix so matching records stack uniformly for UI rendering engine
        compiled_summary.sort(key=lambda x: (x["channel_ref"], x["product_variant"], x["ring_type"]))
        MASTER_CACHE = compiled_summary
        LAST_REFRESH = datetime.now()
        print(f"✅ TBE Engine synced: {len(MASTER_CACHE)} matrix keys verified.")

    except Exception as e:
        print(f"❌ Critical breakdown inside TBE Engine processing thread: {str(e)}")
    finally:
        IS_UPDATING = False

def build_matrix_row(ch, fam, r_type, total_ring_qty, final_date, family_channel_totals):
    # Establish direct common-link cross-reference to Channel rolled-up data
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

# Execution loops handled via background workers
def background_refresh_loop():
    process_tbe_data()
    while True:
        time.sleep(CACHE_DURATION_MINUTES * 60)
        process_tbe_data()

threading.Thread(target=background_refresh_loop, daemon=True).start()

@router.get("/tbe_all_mos")
def get_tbe_dashboard():
    if not LAST_REFRESH and not MASTER_CACHE:
        return {"status": "initializing", "message": "Compiling data streams...", "data": []}
    return {"status": "success", "last_updated": str(LAST_REFRESH), "data": MASTER_CACHE}
