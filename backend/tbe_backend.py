from fastapi import APIRouter
import pandas as pd
import requests
import io
import threading
import time
import warnings
import math
from datetime import datetime
from collections import defaultdict
from settings import settings

router = APIRouter()

# =========================================================
# GLOBAL CACHE & THREADING CONFIG
# =========================================================
MASTER_CACHE = []
LAST_REFRESH = None
IS_UPDATING = False
CACHE_DURATION_MINUTES = 5
INITIALIZATION_FAILED = False  

warnings.filterwarnings('ignore', category=UserWarning, module='openpyxl')

# =========================================================
# CLEANING & PARSING HELPERS
# =========================================================
def extract_val(row, col):
    """Ensures we always get a single scalar value, preventing ambiguous Series errors."""
    if not col: return None
    val = row.get(col)
    return val.iloc[0] if isinstance(val, pd.Series) else val

def clean_mo(value):
    if pd.isna(value):
        return None
    val = str(value).strip().upper().replace(" ", "").replace(".0", "")
    if val in ["NAN", "-", "...", ""] or len(val) < 4:
        return None
    return val

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
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", category=UserWarning)
            parsed = pd.to_datetime(value, errors='coerce', dayfirst=True)
        if pd.isna(parsed):
            return None
        return parsed.date()
    except:
        return None

def normalize_channel(value):
    if pd.isna(value): return ""
    val_str = str(value).strip().upper()
    val_str = val_str.replace("CH-", "").replace("CH", "").replace("-", "").strip()
    if val_str.endswith(".0"):
        val_str = val_str[:-2]
    val_str = val_str.lstrip("0")
    return val_str if val_str else "0"

def parse_family_and_type(prod_text):
    text = normalize_text(prod_text).upper()
    if not text: 
        return "UNKNOWN_FAMILY", "Assembly"
        
    component = "IM" if "IM" in text or "IR" in text else ("OM" if "OM" in text or "OR" in text else "Assembly")
        
    clean = text
    for pfx in ["IM-", "OM-", "IR-", "OR-", "IM", "OM", "IR", "OR"]:
        if clean.startswith(pfx):
            clean = clean[len(pfx):]
            break
    for sfx in ["-IM", "-OM", "-IR", "-OR", "IM", "OM", "IR", "OR"]:
        if clean.endswith(sfx):
            clean = clean[:-len(sfx)]
            break
            
    # Aggressive bearing suffix trimming to prevent 0-quantity cross-sheet mismatches
    clean = clean.split("/")[0]  # Remove /C3, etc.
    clean = clean.replace(" ", "").replace("-", "")
    for sfx in ["2RS1", "2RS", "2Z", "ZZ", "RS", "Z", "C3"]:
        if clean.endswith(sfx) and len(clean) > len(sfx):
            clean = clean[:-len(sfx)]
            break

    clean = clean.strip(" -_")
    return (clean if clean else text), component

def find_column(df, patterns):
    for pattern in patterns:
        for col in df.columns:
            if pattern in str(col).strip().lower():
                return col
    return None

def fix_excel_headers(df):
    if find_column(df, ["type", "variant", "bearing family"]) and find_column(df, ["ch#", "channel", "chan", "ch"]):
        return df.loc[:, ~df.columns.duplicated()]
    
    for i in range(min(15, len(df))):
        row_str = " ".join([str(val).lower() for val in df.iloc[i].values if pd.notna(val)])
        if "type" in row_str and ("ch#" in row_str or "ch" in row_str or "chan" in row_str):
            new_header = df.iloc[i].astype(str).str.strip().str.lower()
            df = df.iloc[i+1:].reset_index(drop=True)
            df.columns = new_header
            return df.loc[:, ~df.columns.duplicated()]
    return df.loc[:, ~df.columns.duplicated()]

def get_channel_info(channel_num, family, channel_data):
    """Smart fallback lookup matching tool to prevent 0-quantity channel data mapping errors."""
    # 1. Direct Match Check
    if (channel_num, family) in channel_data:
        return channel_data[(channel_num, family)]
    
    # 2. Substring/Fuzzy Variant Fallback Map Check
    for (ch, fam), info in channel_data.items():
        if ch == channel_num and (family in fam or fam in family):
            return info
            
    # 3. Channel-wide Match Fallback Check
    ch_records = [info for (ch, fam), info in channel_data.items() if ch == channel_num]
    if ch_records:
        return max(ch_records, key=lambda x: x["max_cum"])
        
    return {"max_cum": None, "in_date": None, "out_date": None}

# =========================================================
# NETWORK EXTRACTION
# =========================================================
def download_excel(url):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    response = requests.get(url, headers=headers, timeout=90)
    if response.status_code != 200:
        raise Exception(f"HTTP {response.status_code}")
    return io.BytesIO(response.content)

def load_excel_sheets(url):
    try:
        excel_data = download_excel(url)
        if "output=csv" in url or "format=csv" in url:
            df = pd.read_csv(excel_data)
            df.columns = [str(c).strip().lower() for c in df.columns]
            return {"Sheet1": df.loc[:, ~df.columns.duplicated()]} 
            
        xls = pd.ExcelFile(excel_data)
        sheets = {}
        for sheet in xls.sheet_names:
            try:
                df = pd.read_excel(xls, sheet_name=sheet)
                df.columns = [str(c).strip().lower() for c in df.columns]
                sheets[sheet] = df.loc[:, ~df.columns.duplicated()]
            except Exception as e:
                print(f"⚠️ Error parsing sheet [{sheet}]: {str(e)}")
        return sheets
    except Exception as e:
        print(f"❌ CRITICAL DOWNLOAD FAILURE: {str(e)}")
        return {}

# =========================================================
# MAIN PROCESSING CORE LOGIC
# =========================================================
def process_tbe_data():
    global MASTER_CACHE, LAST_REFRESH, IS_UPDATING, INITIALIZATION_FAILED
    
    if IS_UPDATING:
        return
    
    IS_UPDATING = True
    print(f"[{datetime.now()}] STARTING TBE EXCEL CACHE REFRESH...")

    try:
        mo_sheets = load_excel_sheets(settings.MO_DATA_URL)
        ring_wt_sheets = load_excel_sheets(settings.RINGWT_TRANSITBUFFER_URL)
        trb_sheets = load_excel_sheets(settings.TRB_MASTER_URL)
        dgbb_sheets = load_excel_sheets(settings.DGBB_MASTER_URL)

        if not ring_wt_sheets:
            print("🚨 ABORTING TBE PARSE: ring_wt_sheets missing.")
            INITIALIZATION_FAILED = True
            return

        # ---------------------------------------------------------
        # 1. PARSE CHANNELS (TRB & DGBB MASTER DATA)
        # ---------------------------------------------------------
        all_channels = {**trb_sheets, **dgbb_sheets}
        channel_data = {}

        for sheet_name, df in all_channels.items():
            df = fix_excel_headers(df)
            
            ch_col = find_column(df, ["ch# no", "ch#", "channel_no", "channel grouping", "channel", "chan", "ch"])
            type_col = find_column(df, ["type", "bearing family", "product", "variant", "item", "family"])
            
            if not ch_col or not type_col: continue

            # Broadened mapping pattern scope to catch standard production volumes
            cum_col = find_column(df, ["cumulative", "cum", "total", "ok", "prod", "quantity", "qty", "output"])
            date_col = find_column(df, ["date"])

            for _, row in df.iterrows():
                channel_num = normalize_channel(extract_val(row, ch_col))
                prod_str = extract_val(row, type_col)
                family, _ = parse_family_and_type(prod_str)
                if not channel_num or not family or family == "UNKNOWN_FAMILY": continue

                cumulative = clean_nan(extract_val(row, cum_col)) if cum_col else 0.0
                date_val = parse_date_safe(extract_val(row, date_col)) if date_col else None

                c_key = (channel_num, family)
                if c_key not in channel_data:
                    channel_data[c_key] = {"max_cum": 0.0, "in_date": None, "out_date": None}
                
                c_meta = channel_data[c_key]
                if cumulative > c_meta["max_cum"]:
                    c_meta["max_cum"] = cumulative
                
                if date_val:
                    c_meta["in_date"] = min(c_meta["in_date"], date_val) if c_meta["in_date"] else date_val
                    c_meta["out_date"] = max(c_meta["out_date"], date_val) if c_meta["out_date"] else date_val

        # ---------------------------------------------------------
        # 2. PARSE MASTER GROUND TRUTH MO DATA MAPS
        # ---------------------------------------------------------
        mo_dict = {}
        for sheet_name, df in mo_sheets.items():
            df = fix_excel_headers(df)
            
            mo_col = find_column(df, ["mo#", "mo number", "mo_num", "mo"])
            prod_col = find_column(df, ["finalvariant", "product", "variant", "type", "item"])
            qty_col = find_column(df, ["qty req", "target qty", "quantity", "qty"])
            if not mo_col or not prod_col: continue

            for _, row in df.iterrows():
                mo_num = clean_mo(extract_val(row, mo_col))
                prod_val = extract_val(row, prod_col)
                family, _ = parse_family_and_type(prod_val)
                target = clean_nan(extract_val(row, qty_col)) if qty_col else 0.0
                
                if family and mo_num:
                    mo_dict[family] = {"mo": mo_num, "target": target}

        # ---------------------------------------------------------
        # 3. PROCESS RING WT TRANSIT BUFFER (WITH 7-DAY GAP CLUSTERING)
        # ---------------------------------------------------------
        raw_transit_entries = []
        
        for sheet_name, df in ring_wt_sheets.items():
            df = fix_excel_headers(df)
            
            ch_col = find_column(df, ["ch# no", "ch#", "channel_no", "channel grouping", "channel", "chan", "ch"])
            type_col = find_column(df, ["type", "bearing family", "product", "variant", "item", "family"])
            qty_col = find_column(df, ["no of rings", "quantity", "qty"]) # Strictly extracts "No Of Rings"
            date_col = find_column(df, ["date", "challan"])
            
            if not ch_col or not type_col: continue
            
            for _, row in df.iterrows():
                channel_num = normalize_channel(extract_val(row, ch_col))
                prod_str = extract_val(row, type_col)
                family, comp_type = parse_family_and_type(prod_str)
                if not channel_num or not family or family == "UNKNOWN_FAMILY": continue

                qty = clean_nan(extract_val(row, qty_col)) if qty_col else 0.0
                date_val = parse_date_safe(extract_val(row, date_col))

                raw_transit_entries.append({
                    "channel_num": channel_num,
                    "family": family,
                    "comp_type": comp_type,
                    "qty": qty,
                    "date": date_val
                })

        # Group raw data by unique ring identifiers
        grouped_raw = defaultdict(list)
        for entry in raw_transit_entries:
            grouped_raw[(entry["channel_num"], entry["family"], entry["comp_type"])].append(entry)

        # ---------------------------------------------------------
        # 4. DATA COMPILATION STAGE WITH ROLLING TIME CLUSTERS
        # ---------------------------------------------------------
        compiled_summary = []
        
        for (channel_num, family, comp_type), entries in grouped_raw.items():
            dated_entries = [e for e in entries if e["date"] is not None]
            undated_entries = [e for e in entries if e["date"] is None]
            
            clusters = []
            if dated_entries:
                # Chronological sort for strict timeline tracking
                dated_entries.sort(key=lambda x: x["date"])
                
                current_cluster = [dated_entries[0]]
                for e in dated_entries[1:]:
                    # Check gap between current item and the latest grouped record
                    gap_days = (e["date"] - current_cluster[-1]["date"]).days
                    if gap_days <= 7:
                        current_cluster.append(e)
                    else:
                        clusters.append(current_cluster)
                        current_cluster = [e]
                clusters.append(current_cluster)

            # Process tracked clusters as separate row entries
            for cluster in clusters:
                total_qty = sum(c["qty"] for c in cluster)
                cluster_dates = [c["date"] for c in cluster]
                min_date = min(cluster_dates)
                max_date = max(cluster_dates)
                
                ch_info = get_channel_info(channel_num, family, channel_data)
                mo_info = mo_dict.get(family, {"mo": "", "target": 0.0})
                
                calc_status = "In Process"
                if ch_info["max_cum"] is not None and ch_info["max_cum"] >= total_qty and total_qty > 0:
                    calc_status = "Completed"
                elif total_qty == 0 and ch_info["max_cum"] in (None, 0):
                    calc_status = "Yet to Start"

                compiled_summary.append({
                    "mo_number": mo_info["mo"],
                    "product_variant": family,
                    "target_qty": int(mo_info["target"]) if mo_info["target"] > 0 else "",
                    "ring_type": comp_type,
                    "sho_qty": total_qty if total_qty > 0 else "", 
                    "sho_in": str(min_date) if min_date else "-",
                    "tb_qty": total_qty if total_qty > 0 else "",
                    "tb_out": str(max_date) if max_date else "-",
                    "ch_qty": int(ch_info["max_cum"]) if ch_info["max_cum"] is not None and ch_info["max_cum"] > 0 else "",
                    "ch_in": str(ch_info["in_date"]) if ch_info["in_date"] else "-",
                    "ch_out": str(ch_info["out_date"]) if ch_info["out_date"] else "-",
                    "status": calc_status,
                    "channel_ref": channel_num
                })

            # Process undated rows safely so no data points are missed
            if undated_entries:
                total_qty = sum(u["qty"] for u in undated_entries)
                ch_info = get_channel_info(channel_num, family, channel_data)
                mo_info = mo_dict.get(family, {"mo": "", "target": 0.0})
                
                calc_status = "In Process"
                if ch_info["max_cum"] is not None and ch_info["max_cum"] >= total_qty and total_qty > 0:
                    calc_status = "Completed"

                compiled_summary.append({
                    "mo_number": mo_info["mo"],
                    "product_variant": family,
                    "target_qty": int(mo_info["target"]) if mo_info["target"] > 0 else "",
                    "ring_type": comp_type,
                    "sho_qty": total_qty if total_qty > 0 else "", 
                    "sho_in": "-",
                    "tb_qty": total_qty if total_qty > 0 else "",
                    "tb_out": "-",
                    "ch_qty": int(ch_info["max_cum"]) if ch_info["max_cum"] is not None and ch_info["max_cum"] > 0 else "",
                    "ch_in": str(ch_info["in_date"]) if ch_info["in_date"] else "-",
                    "ch_out": str(ch_info["out_date"]) if ch_info["out_date"] else "-",
                    "status": calc_status,
                    "channel_ref": channel_num
                })

        compiled_summary.sort(key=lambda x: (x["mo_number"], x["product_variant"], x["ring_type"]))
        
        MASTER_CACHE = compiled_summary
        INITIALIZATION_FAILED = False
        LAST_REFRESH = datetime.now()
        print(f"[{datetime.now()}] SUCCESS: TBE MATRIX SYNCHRONIZED. ROWS PROCESSED: {len(MASTER_CACHE)}")

    except Exception as e:
        print(f"CRITICAL TBE DATA THREAD ERROR: {str(e)}")
        INITIALIZATION_FAILED = True
    finally:
        IS_UPDATING = False

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
        if INITIALIZATION_FAILED:
            return {
                "status": "failed",
                "message": "Data stream extraction failed. Look at your server terminal logs right now to see the error.",
                "data": []
            }
        return {
            "status": "initializing",
            "message": "System maps are being prepared. Please hold...",
            "data": []
        }
    return {
        "status": "success",
        "last_updated": str(LAST_REFRESH),
        "data": MASTER_CACHE
    }
