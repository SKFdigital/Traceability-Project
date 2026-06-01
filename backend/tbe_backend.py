from fastapi import APIRouter
import pandas as pd
import requests
import io
import threading
import time
import warnings
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
INITIALIZATION_FAILED = False  

warnings.filterwarnings('ignore', category=UserWarning, module='openpyxl')

# =========================================================
# CLEANING & PARSING HELPERS
# =========================================================
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
            
    clean = clean.strip(" -_")
    return (clean if clean else text), component

def find_column(df, patterns):
    for col in df.columns:
        col_clean = str(col).strip().lower()
        for pattern in patterns:
            if pattern in col_clean:
                return col
    return None

def fix_excel_headers(df):
    if find_column(df, ["type", "variant", "bearing family"]) and find_column(df, ["ch#", "channel", "chan", "ch"]):
        return df
    
    for i in range(min(15, len(df))):
        row_str = " ".join([str(val).lower() for val in df.iloc[i].values if pd.notna(val)])
        if "type" in row_str and ("ch#" in row_str or "ch" in row_str or "chan" in row_str):
            new_header = df.iloc[i].astype(str).str.strip().str.lower()
            df = df.iloc[i+1:].reset_index(drop=True)
            df.columns = new_header
            return df
    return df

# =========================================================
# NETWORK EXTRACTION (WITH BROWSER SPOOFING & TIMEOUTS)
# =========================================================
def download_excel(url):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Cache-Control": "no-cache"
    }
    
    print(f"🔄 Requesting download from destination: {url}")
    response = requests.get(url, headers=headers, timeout=90)
    
    if response.status_code != 200:
        print(f"🚨 NETWORK INTERCEPTED REQUEST! Status Code: {response.status_code}")
        print(f"Server Response Snippet: {response.text[:300]}")
        raise Exception(f"HTTP {response.status_code}")
        
    return io.BytesIO(response.content)

def load_excel_sheets(url):
    try:
        excel_data = download_excel(url)
        
        # Smart detection: Parse instantly if URL targets a CSV stream
        if "output=csv" in url or "format=csv" in url:
            df = pd.read_csv(excel_data)
            df.columns = [str(c).strip().lower() for c in df.columns]
            print("✅ Web CSV data stream extracted successfully.")
            return {"Sheet1": df} 
            
        # Default processing for standard Excel files
        xls = pd.ExcelFile(excel_data)
        sheets = {}
        for sheet in xls.sheet_names:
            try:
                df = pd.read_excel(xls, sheet_name=sheet)
                df.columns = [str(c).strip().lower() for c in df.columns]
                sheets[sheet] = df
            except Exception as e:
                print(f"⚠️ Error parsing sheet [{sheet}]: {str(e)}")
        print(f"✅ Workbook parsed successfully. Found {len(sheets)} sheets.")
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

        print("\n--- DIAGNOSTIC DATA CHECK ---")
        print(f"MO Sheets Found: {bool(mo_sheets)}")
        print(f"Ring Wt Sheets Found: {bool(ring_wt_sheets)}")
        print(f"TRB Sheets Found: {bool(trb_sheets)}")
        print(f"DGBB Sheets Found: {bool(dgbb_sheets)}")
        print("-----------------------------\n")

        if not ring_wt_sheets:
            print("🚨 ABORTING TBE PARSE: ring_wt_sheets is totally missing. Pipeline cannot build anchor fields.")
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

            cum_col = find_column(df, ["cumulative", "cum"])
            prod_col = find_column(df, ["production", "prod"])
            date_col = find_column(df, ["date"])

            for _, row in df.iterrows():
                channel_num = normalize_channel(row.get(ch_col))
                prod_str = row.get(type_col)
                family, _ = parse_family_and_type(prod_str)
                if not channel_num or not family or family == "UNKNOWN_FAMILY": continue

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
            df = fix_excel_headers(df)
            
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
            df = fix_excel_headers(df)
            
            ch_col = find_column(df, ["ch# no", "ch#", "channel_no", "channel grouping", "channel", "chan", "ch"])
            type_col = find_column(df, ["type", "bearing family", "product", "variant", "item", "family"])
            qty_col = find_column(df, ["qty", "quantity", "no of rings", "net wt"])
            date_col = find_column(df, ["date", "challan"])
            
            if not ch_col or not type_col: continue
            
            for _, row in df.iterrows():
                channel_num = normalize_channel(row.get(ch_col))
                prod_str = row.get(type_col)
                family, comp_type = parse_family_and_type(prod_str)
                if not channel_num or not family or family == "UNKNOWN_FAMILY": continue

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
            if ch_info["max_cum"] is not None and ch_info["max_cum"] >= rw_data["qty"] and rw_data["qty"] > 0:
                calc_status = "Completed"
            elif rw_data["qty"] == 0 and ch_info["max_cum"] in (None, 0):
                calc_status = "Yet to Start"

            compiled_summary.append({
                "mo_number": mo_info["mo"],
                "product_variant": family,
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
