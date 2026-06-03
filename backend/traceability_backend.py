from fastapi import APIRouter, HTTPException
import pandas as pd
import requests
import io
import threading
import time
import math
import re
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
    if val in ["NAN", "-", "...", ""]: return None
    return val

def get_mo_group(clean_mo_str):
    # Removed the aggressive regex slicing that was breaking MO grouping and ring counts.
    # Now returns the exact cleaned MO string for accurate 1:1 mapping.
    return clean_mo_str

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

def determine_component(text):
    text = str(text).strip().upper()
    if "OM" in text or "OUTER" in text: return "OM"
    return "IM" # Default Inner Module

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

def ensure_mo_in_summary(summary_map, mo_group, base_product="Generic Product"):
    """Helper to ensure MO exists in summary even if missing from MO_Data sheet"""
    if mo_group not in summary_map:
        summary_map[mo_group] = {
            "mo": mo_group, 
            "base_product": base_product, 
            "ch_qty": 0.0, 
            "ch_date": None,
            "components": {
                "IM": {"qty_req": 0, "sho": 0, "sho_d": "-", "tb": 0, "tb_d": "-"},
                "OM": {"qty_req": 0, "sho": 0, "sho_d": "-", "tb": 0, "tb_d": "-"}
            }
        }
    return summary_map[mo_group]

def process_traceability_data():
    global MASTER_CACHE, LAST_REFRESH, IS_UPDATING, INITIALIZED, GLOBAL_RAW_RECORDS
    if IS_UPDATING: return
    IS_UPDATING = True

    try:
        mo_sheets = load_excel_sheets(settings.MO_DATA_URL)
        jobwork_sheets = load_excel_sheets(settings.JOBWORK_REPORT_URL)
        trb_sheets = load_excel_sheets(settings.TRB_MASTER_URL)
        dgbb_sheets = load_excel_sheets(settings.DGBB_MASTER_URL)

        summary_map = {}
        raw_mo_data = []
        raw_jw_data = []
        raw_ch_data = []

        # 1. MO Data (Extract Target Qty & IM/OM)
        for _, df in mo_sheets.items():
            if "mo#" not in df.columns: continue
            
            # Apply PDIV Filter (Exclude everything except 227D and 227T)
            if "pdiv" in df.columns:
                df["pdiv"] = df["pdiv"].fillna("").astype(str).str.strip().str.upper()
                df = df[df["pdiv"].isin(["227D", "227T"])]

            for _, row in df.iterrows():
                raw_mo = clean_mo(row.get("mo#"))
                if not raw_mo: continue
                
                mo_group = get_mo_group(raw_mo)
                qty_req = clean_nan(row.get("qty req") if "qty req" in df.columns else 0)
                final_variant = str(row.get("finalvariant")).strip() if "finalvariant" in df.columns and not pd.isna(row.get("finalvariant")) else "Generic Product"
                
                comp_raw = row.get("comp item") if "comp item" in df.columns else ""
                comp_type = determine_component(comp_raw)
                
                raw_mo_data.append({
                    "mo_group": mo_group, "variant": final_variant, 
                    "comp_type": comp_type, "qty_req": qty_req
                })

                data = ensure_mo_in_summary(summary_map, mo_group, final_variant)
                data["components"][comp_type]["qty_req"] += qty_req

        # 2. JobWork Data (SHO & TB mapping by IM/OM)
        for _, df in jobwork_sheets.items():
            if "po / pr no." not in df.columns: continue
            for _, row in df.iterrows():
                raw_mo = clean_mo(row.get("po / pr no."))
                if not raw_mo: continue
                
                mo_group = get_mo_group(raw_mo)
                variant = str(row.get("product")).strip() if "product" in df.columns and not pd.isna(row.get("product")) else "Generic Product"
                comp_type = determine_component(variant)

                sho_qty = clean_nan(row.get("qty approved") if "qty approved" in df.columns else 0)
                tb_qty = clean_nan(row.get("qty returned") if "qty returned" in df.columns else 0)
                sho_date = parse_date_safe(row.get("jw challan date") if "jw challan date" in df.columns else None)
                tb_date = parse_date_safe(row.get("last challan date") if "last challan date" in df.columns else None)

                raw_jw_data.append({
                    "mo_group": mo_group, "variant": variant, "comp_type": comp_type,
                    "sho_qty": sho_qty, "tb_qty": tb_qty, "sho_date": sho_date, "tb_date": tb_date
                })

                # Always process JW even if MO wasn't in MO_Data
                data = ensure_mo_in_summary(summary_map, mo_group, variant)
                data["components"][comp_type]["sho"] += sho_qty
                data["components"][comp_type]["tb"] += tb_qty
                if sho_date: data["components"][comp_type]["sho_d"] = str(sho_date)
                if tb_date: data["components"][comp_type]["tb_d"] = str(tb_date)

        # 3. Channel Data (Unified)
        all_channels = {**trb_sheets, **dgbb_sheets}
        for _, df in all_channels.items():
            if "mo" not in df.columns: continue
            type_col = "type" if "type" in df.columns else ("product" if "product" in df.columns else None)
            
            for _, row in df.iterrows():
                raw_mo = clean_mo(row.get("mo"))
                if not raw_mo: continue
                
                mo_group = get_mo_group(raw_mo)
                variant = str(row.get(type_col)).strip() if type_col and not pd.isna(row.get(type_col)) else "Generic Product"
                ch_qty = clean_nan(row.get("cumulative production") if "cumulative production" in df.columns else 0)
                ch_date = parse_date_safe(row.get("date") if "date" in df.columns else None)

                raw_ch_data.append({
                    "mo_group": mo_group, "variant": variant, "ch_qty": ch_qty, "ch_date": ch_date
                })

                # Always process Channel data even if MO wasn't in MO_Data
                data = ensure_mo_in_summary(summary_map, mo_group, variant)
                if ch_qty > data["ch_qty"]:
                    data["ch_qty"] = ch_qty
                if ch_date: 
                    data["ch_date"] = str(ch_date)

        # Build Flat List for Table
        compiled_summary = []
        for mo, data in summary_map.items():
            im = data["components"]["IM"]
            om = data["components"]["OM"]
            req = max(im["qty_req"], om["qty_req"])
            
            status = "Completed" if (data["ch_qty"] >= req and req > 0) else ("In Process" if (im["sho"] > 0 or om["sho"] > 0) else "Yet to Start")

            if im["qty_req"] > 0 or im["sho"] > 0 or data["ch_qty"] > 0:
                compiled_summary.append({
                    "mo": mo, "base_product": data["base_product"], "component": "IM",
                    "qty_req": math.ceil(im["qty_req"]), "sho_qty": math.ceil(im["sho"]), "sho_date": im["sho_d"],
                    "tb_qty": math.ceil(im["tb"]), "tb_date": im["tb_d"],
                    "ch_qty": math.ceil(data["ch_qty"]), "ch_date": data["ch_date"] or "-", "status": status
                })
            
            if om["qty_req"] > 0 or om["sho"] > 0:
                compiled_summary.append({
                    "mo": mo, "base_product": data["base_product"], "component": "OM",
                    "qty_req": math.ceil(om["qty_req"]), "sho_qty": math.ceil(om["sho"]), "sho_date": om["sho_d"],
                    "tb_qty": math.ceil(om["tb"]), "tb_date": om["tb_d"],
                    "ch_qty": math.ceil(data["ch_qty"]), "ch_date": data["ch_date"] or "-", "status": status
                })

        compiled_summary.sort(key=lambda x: (x["mo"], x["component"]))
        
        MASTER_CACHE = compiled_summary
        GLOBAL_RAW_RECORDS = {"mo_data": raw_mo_data, "jw_data": raw_jw_data, "ch_data": raw_ch_data}
        LAST_REFRESH = datetime.now()
        INITIALIZED = True

    except Exception as e:
        print(f"❌ PIPELINE ERROR: {str(e)}")
    finally:
        IS_UPDATING = False

def background_refresh_loop():
    process_traceability_data()
    while True:
        time.sleep(CACHE_DURATION_MINUTES * 60)
        process_traceability_data()

threading.Thread(target=background_refresh_loop, daemon=True).start()

@router.get("/traceability_all_mos")
def get_all_mos():
    if not INITIALIZED:
        return {"status": "initializing", "data": []}
    return {"status": "success", "data": MASTER_CACHE}

@router.get("/traceability_report/{mo}")
def get_traceability_flow(mo: str):
    search_group = get_mo_group(clean_mo(mo))
    variant_map = {}

    def get_var(v_dict, v_name):
        if v_name not in v_dict:
            v_dict[v_name] = {
                "ch_qty": 0, "ch_date": None,
                "components": {
                    "IM": {"qty_req": 0, "sho": 0, "sho_d": "-", "tb": 0, "tb_d": "-"},
                    "OM": {"qty_req": 0, "sho": 0, "sho_d": "-", "tb": 0, "tb_d": "-"}
                }
            }
        return v_dict[v_name]

    def find_match(target, current_map):
        if target in current_map: return target
        for k in current_map.keys():
            if target and target in k: return k
        return list(current_map.keys())[0] if current_map else target

    # Map Variants & Targets
    for r in GLOBAL_RAW_RECORDS["mo_data"]:
        if r["mo_group"] == search_group:
            v_name = r["variant"] if r["variant"] else "Generic Variant"
            v = get_var(variant_map, v_name)
            v["components"][r["comp_type"]]["qty_req"] += r["qty_req"]

    # Map SHO/TB Jobwork
    for r in GLOBAL_RAW_RECORDS["jw_data"]:
        if r["mo_group"] == search_group:
            v_name = find_match(r["variant"], variant_map)
            v = get_var(variant_map, v_name)
            c = r["comp_type"]
            v["components"][c]["sho"] += r["sho_qty"]
            v["components"][c]["tb"] += r["tb_qty"]
            if r["sho_date"]: v["components"][c]["sho_d"] = str(r["sho_date"])
            if r["tb_date"]: v["components"][c]["tb_d"] = str(r["tb_date"])

    # Map Channels
    for r in GLOBAL_RAW_RECORDS["ch_data"]:
        if r["mo_group"] == search_group:
            v_name = find_match(r["variant"], variant_map)
            v = get_var(variant_map, v_name)
            if r["ch_qty"] > v["ch_qty"]:
                v["ch_qty"] = r["ch_qty"]
            if r["ch_date"]: v["ch_date"] = str(r["ch_date"])

    # Build Exact TBE Sequential Data Model for Frontend Drilldown
    rows = []
    for var_name, data in variant_map.items():
        im = data["components"]["IM"]
        om = data["components"]["OM"]
        
        # 1. IM Workflows
        if im["sho"] > 0:
            rows.append({"mo_ref": search_group, "department": "SHO Department", "variant": f"IM - {var_name}", "in_date": im["sho_d"], "out_date": "-", "qty": math.ceil(im["sho"]), "status": "Allocated"})
        if im["tb"] > 0:
            rows.append({"mo_ref": search_group, "department": "Transit Buffer", "variant": f"IM - {var_name}", "in_date": "-", "out_date": im["tb_d"], "qty": math.ceil(im["tb"]), "status": "In Transit"})
            
        # 2. OM Workflows
        if om["sho"] > 0:
            rows.append({"mo_ref": search_group, "department": "SHO Department", "variant": f"OM - {var_name}", "in_date": om["sho_d"], "out_date": "-", "qty": math.ceil(om["sho"]), "status": "Allocated"})
        if om["tb"] > 0:
            rows.append({"mo_ref": search_group, "department": "Transit Buffer", "variant": f"OM - {var_name}", "in_date": "-", "out_date": om["tb_d"], "qty": math.ceil(om["tb"]), "status": "In Transit"})
            
        # 3. Channel Pipeline
        if data["ch_qty"] > 0:
            rows.append({"mo_ref": search_group, "department": "Channel Section", "variant": var_name, "in_date": data.get("ch_date") or "-", "out_date": "-", "qty": math.ceil(data["ch_qty"]), "status": "Completed"})

    return {"status": "success", "data": {"mo": search_group, "rows": rows}}
