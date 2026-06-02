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

MASTER_CACHE = []
LAST_REFRESH = None
IS_UPDATING = False
INITIALIZED = False
CACHE_DURATION_MINUTES = 5

GLOBAL_RAW_RECORDS = {"mo_data": [], "jw_data": [], "ch_data": []}
HTTP_SESSION = requests.Session()

def clean_mo(value):
    if pd.isna(value): return None
    val = str(value).strip().upper().replace(" ", "").replace(".0", "")
    if val in ["NAN", "-", "...", ""] or len(val) < 4: return None
    return val

def get_mo_group(clean_mo_str):
    return clean_mo_str[:4] if clean_mo_str and len(clean_mo_str) >= 4 else clean_mo_str

def clean_nan(value):
    try:
        if pd.isna(value) or str(value).strip().lower() in ['nan', '-', '...', '']: return 0.0
        f_val = float(value)
        return 0.0 if math.isnan(f_val) else f_val
    except:
        return 0.0

def parse_date_safe(value):
    try:
        if pd.isna(value) or str(value).strip().lower() in ["nan", "nat", "", "-"]: return None
        parsed = pd.to_datetime(value, errors='coerce', dayfirst=True)
        return parsed.date() if not pd.isna(parsed) else None
    except:
        return None

def parse_product_details(prod_text):
    text = str(prod_text).strip().upper() if not pd.isna(prod_text) else ""
    base_product = text if text else "Gen Product"
    return base_product

def load_excel_sheets(url):
    try:
        resp = HTTP_SESSION.get(url, timeout=30)
        if resp.status_code != 200: return {}
        xls = pd.ExcelFile(io.BytesIO(resp.content))
        sheets = {}
        for sheet in xls.sheet_names:
            df = pd.read_excel(xls, sheet_name=sheet)
            df.columns = [str(c).strip().lower() for c in df.columns]
            sheets[sheet] = df
        return sheets
    except:
        return {}

def process_traceability_data():
    global MASTER_CACHE, LAST_REFRESH, IS_UPDATING, INITIALIZED, GLOBAL_RAW_RECORDS
    if IS_UPDATING: return
    IS_UPDATING = True

    try:
        mo_sheets = load_excel_sheets(settings.MO_DATA_URL)
        jobwork_sheets = load_excel_sheets(settings.JOBWORK_REPORT_URL)
        trb_sheets = load_excel_sheets(settings.TRB_MASTER_URL)
        dgbb_sheets = load_excel_sheets(settings.DGBB_MASTER_URL)

        summary_aggregation = {}
        raw_mo_data = []
        raw_jw_data = []
        raw_ch_data = []

        # 1. MO Data (Target Qty Mapping)
        for _, df in mo_sheets.items():
            if "mo#" not in df.columns or "comp item" not in df.columns: continue
            for _, row in df.iterrows():
                raw_mo = clean_mo(row.get("mo#"))
                if not raw_mo: continue
                
                mo_group = get_mo_group(raw_mo)
                qty_req = clean_nan(row.get("qty req"))
                final_variant = str(row.get("finalvariant")).strip() if not pd.isna(row.get("finalvariant")) else ""
                base_prod = parse_product_details(final_variant)
                
                raw_mo_data.append({
                    "mo_group": mo_group, "full_mo": raw_mo, "variant": final_variant, 
                    "base_prod": base_prod, "qty_req": qty_req
                })

                # Group strictly by MO and Base Product (Family) - NO component splitting
                sum_key = (mo_group, base_prod)
                if sum_key not in summary_aggregation:
                    summary_aggregation[sum_key] = {
                        "mo": mo_group, "base_product": base_prod, "qty_req": 0.0,
                        "sho_qty": 0.0, "sho_date": None, "tb_qty": 0.0, "tb_date": None,
                        "ch_qty": 0.0, "ch_date": None
                    }
                summary_aggregation[sum_key]["qty_req"] += qty_req

        # 2. JobWork Data (SHO & TB)
        for _, df in jobwork_sheets.items():
            if "po / pr no." not in df.columns: continue
            for _, row in df.iterrows():
                raw_mo = clean_mo(row.get("po / pr no."))
                if not raw_mo: continue
                
                mo_group = get_mo_group(raw_mo)
                variant = str(row.get("product")).strip() if not pd.isna(row.get("product")) else ""
                base_prod = parse_product_details(variant)
                sho_qty = clean_nan(row.get("qty approved"))
                tb_qty = clean_nan(row.get("qty returned"))
                sho_date = parse_date_safe(row.get("jw challan date"))
                tb_date = parse_date_safe(row.get("last challan date"))

                raw_jw_data.append({
                    "mo_group": mo_group, "full_mo": raw_mo, "variant": variant, 
                    "base_prod": base_prod, "sho_qty": sho_qty, "tb_qty": tb_qty,
                    "sho_date": sho_date, "tb_date": tb_date
                })

                sum_key = (mo_group, base_prod)
                if sum_key in summary_aggregation:
                    summary_aggregation[sum_key]["sho_qty"] += sho_qty
                    summary_aggregation[sum_key]["tb_qty"] += tb_qty
                    if sho_date: summary_aggregation[sum_key]["sho_date"] = sho_date
                    if tb_date: summary_aggregation[sum_key]["tb_date"] = tb_date

        # 3. Channel Data
        all_channels = {**trb_sheets, **dgbb_sheets}
        for _, df in all_channels.items():
            if "mo" not in df.columns: continue
            type_col = "type" if "type" in df.columns else ("product" if "product" in df.columns else None)
            if not type_col: continue

            for _, row in df.iterrows():
                raw_mo = clean_mo(row.get("mo"))
                if not raw_mo: continue
                
                mo_group = get_mo_group(raw_mo)
                variant = str(row.get(type_col)).strip() if not pd.isna(row.get(type_col)) else ""
                base_prod = parse_product_details(variant)
                ch_qty = clean_nan(row.get("cumulative production"))
                ch_date = parse_date_safe(row.get("date"))

                raw_ch_data.append({
                    "mo_group": mo_group, "full_mo": raw_mo, "variant": variant, 
                    "base_prod": base_prod, "ch_qty": ch_qty, "ch_date": ch_date
                })

                sum_key = (mo_group, base_prod)
                if sum_key in summary_aggregation:
                    if ch_qty > summary_aggregation[sum_key]["ch_qty"]:
                        summary_aggregation[sum_key]["ch_qty"] = ch_qty
                    if ch_date: summary_aggregation[sum_key]["ch_date"] = ch_date

        compiled_summary = []
        for _, data in summary_aggregation.items():
            status = "Completed" if (data["ch_qty"] >= data["sho_qty"] and data["sho_qty"] > 0) else ("In Process" if data["sho_qty"] > 0 else "Yet to Start")
            compiled_summary.append({
                "mo": data["mo"],
                "base_product": data["base_product"],
                "qty_req": math.ceil(data["qty_req"]),
                "sho_qty": math.ceil(data["sho_qty"]),
                "sho_date": str(data["sho_date"]) if data["sho_date"] else "-",
                "tb_qty": math.ceil(data["tb_qty"]),
                "tb_date": str(data["tb_date"]) if data["tb_date"] else "-",
                "ch_qty": math.ceil(data["ch_qty"]),
                "ch_date": str(data["ch_date"]) if data["ch_date"] else "-",
                "status": status
            })

        compiled_summary.sort(key=lambda x: (x["mo"], x["base_product"]))
        
        MASTER_CACHE = compiled_summary
        GLOBAL_RAW_RECORDS = {"mo_data": raw_mo_data, "jw_data": raw_jw_data, "ch_data": raw_ch_data}
        LAST_REFRESH = datetime.now()
        INITIALIZED = True

    except Exception as e:
        print(f"❌ PIPELINE ERROR: {str(e)}")
    finally:
        IS_UPDATING = False

# Defined BEFORE calling inside thread registration block to avoid execution NameError bugs
def background_refresh_loop():
    process_traceability_data()
    while True:
        time.sleep(CACHE_DURATION_MINUTES * 60)
        process_traceability_data()

# Starts engine execution thread pool safely
threading.Thread(target=background_refresh_loop, daemon=True).start()

@router.get("/traceability_all_mos")
def get_all_mos():
    if not INITIALIZED:
        return {"status": "initializing", "data": []}
    return {"status": "success", "data": MASTER_CACHE}

@router.get("/traceability_report/{mo}")
def get_traceability_flow(mo: str):
    """
    Maps the breakdown of detailed variants belonging to this MO Group.
    """
    search_group = get_mo_group(clean_mo(mo))
    variant_map = {}

    # Target Quantities
    for r in GLOBAL_RAW_RECORDS["mo_data"]:
        if r["mo_group"] == search_group:
            v = r["variant"]
            if v not in variant_map:
                variant_map[v] = {"variant": v, "qty_req": 0, "sho_qty": 0, "sho_date": "-", "tb_qty": 0, "tb_date": "-", "ch_qty": 0, "ch_date": "-"}
            variant_map[v]["qty_req"] += r["qty_req"]

    # JobWork (SHO & TB) Quantities
    for r in GLOBAL_RAW_RECORDS["jw_data"]:
        if r["mo_group"] == search_group:
            v = r["variant"]
            if v not in variant_map:
                variant_map[v] = {"variant": v, "qty_req": 0, "sho_qty": 0, "sho_date": "-", "tb_qty": 0, "tb_date": "-", "ch_qty": 0, "ch_date": "-"}
            variant_map[v]["sho_qty"] += r["sho_qty"]
            variant_map[v]["tb_qty"] += r["tb_qty"]
            if r["sho_date"]: variant_map[v]["sho_date"] = str(r["sho_date"])
            if r["tb_date"]: variant_map[v]["tb_date"] = str(r["tb_date"])

    # Channel Quantities
    for r in GLOBAL_RAW_RECORDS["ch_data"]:
        if r["mo_group"] == search_group:
            v = r["variant"]
            if v not in variant_map:
                variant_map[v] = {"variant": v, "qty_req": 0, "sho_qty": 0, "sho_date": "-", "tb_qty": 0, "tb_date": "-", "ch_qty": 0, "ch_date": "-"}
            if r["ch_qty"] > variant_map[v]["ch_qty"]:
                variant_map[v]["ch_qty"] = r["ch_qty"]
            if r["ch_date"]: variant_map[v]["ch_date"] = str(r["ch_date"])

    rows = []
    for k, v in variant_map.items():
        if v["qty_req"] == 0 and v["sho_qty"] == 0 and v["ch_qty"] == 0: continue
        status = "Completed" if (v["ch_qty"] >= v["sho_qty"] and v["sho_qty"] > 0) else ("In Process" if v["sho_qty"] > 0 else "Yet to Start")
        
        rows.append({
            "variant": v["variant"],
            "qty_req": math.ceil(v["qty_req"]),
            "sho_qty": math.ceil(v["sho_qty"]),
            "sho_date": v["sho_date"],
            "tb_qty": math.ceil(v["tb_qty"]),
            "tb_date": v["tb_date"],
            "ch_qty": math.ceil(v["ch_qty"]),
            "ch_date": v["ch_date"],
            "status": status
        })

    rows.sort(key=lambda x: x["variant"])

    return {
        "status": "success",
        "data": {
            "mo": search_group,
            "rows": rows
        }
    }
