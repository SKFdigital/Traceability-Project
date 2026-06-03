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
    """Aggressively checks and cleans MO strings. Returns None for blanks/NaNs to prevent ghost records."""
    if pd.isna(value): return None
    val = str(value).strip().upper().replace(" ", "")
    if val.endswith(".0"): 
        val = val[:-2]
    if not val or val in ["NAN", "-", "...", "", "NAT", "NONE"]: 
        return None
    if len(val) < 3: 
        return None # Prevents stray 1-2 character anomalies from creating ghost groups
    return val

def get_mo_group(clean_mo_str):
    if not clean_mo_str: return None
    match = re.match(r'^(\d{4,})', clean_mo_str)
    group = match.group(1) if match else clean_mo_str[:4] if len(clean_mo_str) >= 4 else clean_mo_str
    if not group or group.strip() == "": return None
    return group

def clean_family_name(text):
    """Strictly isolates the bearing family number (e.g., '6007') and discards garbage text."""
    if pd.isna(text): return "Unknown Bearing"
    t = str(text).upper()
    
    # Clean out known garbage words first
    t = re.sub(r'(?i)(NORMAL|INNER|OUTER|GENERIC PRODUCT)', '', t)
    
    # Extract the bearing number sequence (3 or more digits + optional trailing characters)
    match = re.search(r'(\d{3,}[A-Z0-9\-]*)', t)
    if match:
        core = match.group(1)
        # Strip trailing IM/OM if physically attached to the digits (e.g., '6007IM' -> '6007')
        core = re.sub(r'(?i)(IM|OM)$', '', core)
        return core.strip('- ')
        
    return "Unknown Bearing"

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
    return "IM" 

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
    except Exception as e:
        print(f"Error loading {url}: {e}")
        return {}

def ensure_mo_in_summary(summary_map, mo_group, potential_family="Unknown Bearing"):
    if mo_group not in summary_map:
        summary_map[mo_group] = {
            "mo": mo_group, 
            "base_product": potential_family, 
            "ch_qty": 0.0, 
            "ch_date_max": None,
            "components": {
                "IM": {"qty_req": 0, "sho": 0, "sho_d": "-", "tb": 0, "tb_d": "-"},
                "OM": {"qty_req": 0, "sho": 0, "sho_d": "-", "tb": 0, "tb_d": "-"}
            }
        }
    else:
        if potential_family != "Unknown Bearing" and summary_map[mo_group]["base_product"] == "Unknown Bearing":
            summary_map[mo_group]["base_product"] = potential_family
            
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

        # 1. MO Data
        for _, df in mo_sheets.items():
            if "mo#" not in df.columns: continue
            
            if "pdiv" in df.columns:
                df["pdiv"] = df["pdiv"].fillna("").astype(str).str.strip().str.upper()
                df = df[df["pdiv"].isin(["227D", "227T"])]

            for row in df.to_dict('records'):
                raw_mo = clean_mo(row.get("mo#"))
                if not raw_mo: continue
                
                mo_group = get_mo_group(raw_mo)
                if not mo_group: continue
                
                # FIXED: Safely process component without skipping valid rows
                comp_raw = str(row.get("comp item", "")).strip()
                comp_type = determine_component(comp_raw)
                
                qty_req = clean_nan(row.get("qty req", 0))
                final_variant = clean_family_name(row.get("finalvariant"))
                
                raw_mo_data.append({"mo_group": mo_group, "variant": final_variant, "comp_type": comp_type, "qty_req": qty_req})

                data = ensure_mo_in_summary(summary_map, mo_group, final_variant)
                
                # EXACT ASSIGNMENT: Directly sets the target quantity per your instructions
                data["components"][comp_type]["qty_req"] = qty_req

        # 2. JobWork Data
        for _, df in jobwork_sheets.items():
            if "po / pr no." not in df.columns: continue
            for row in df.to_dict('records'):
                raw_mo = clean_mo(row.get("po / pr no."))
                if not raw_mo: continue
                
                mo_group = get_mo_group(raw_mo)
                if not mo_group: continue
                
                raw_product = row.get("product", "")
                variant = clean_family_name(raw_product)
                comp_type = determine_component(raw_product)

                sho_qty = clean_nan(row.get("qty approved", 0))
                tb_qty = clean_nan(row.get("qty returned", 0))
                sho_date = parse_date_safe(row.get("jw challan date"))
                tb_date = parse_date_safe(row.get("last challan date"))

                raw_jw_data.append({
                    "mo_group": mo_group, "variant": variant, "comp_type": comp_type,
                    "sho_qty": sho_qty, "tb_qty": tb_qty, "sho_date": sho_date, "tb_date": tb_date
                })

                data = ensure_mo_in_summary(summary_map, mo_group, variant)
                data["components"][comp_type]["sho"] += sho_qty
                data["components"][comp_type]["tb"] += tb_qty
                if sho_date: data["components"][comp_type]["sho_d"] = str(sho_date)
                if tb_date: data["components"][comp_type]["tb_d"] = str(tb_date)

        # 3. Channel Data 
        all_channels = {**trb_sheets, **dgbb_sheets}
        for _, df in all_channels.items():
            if "mo" not in df.columns: continue
            type_col = "type" if "type" in df.columns else ("product" if "product" in df.columns else None)
            
            for row in df.to_dict('records'):
                raw_mo = clean_mo(row.get("mo"))
                if not raw_mo: continue
                
                mo_group = get_mo_group(raw_mo)
                if not mo_group: continue
                
                variant = clean_family_name(row.get(type_col)) if type_col else "Unknown Bearing"
                ch_qty = clean_nan(row.get("production", 0))
                ch_date = parse_date_safe(row.get("date"))

                raw_ch_data.append({"mo_group": mo_group, "variant": variant, "ch_qty": ch_qty, "ch_date": ch_date})

                data = ensure_mo_in_summary(summary_map, mo_group, variant)
                data["ch_qty"] += ch_qty
                
                if ch_date:
                    if not data["ch_date_max"] or ch_date > data["ch_date_max"]:
                        data["ch_date_max"] = ch_date

        compiled_summary = []
        for mo, data in summary_map.items():
            im = data["components"]["IM"]
            om = data["components"]["OM"]
            req = max(im["qty_req"], om["qty_req"])
            
            status = "Completed" if (data["ch_qty"] >= req and req > 0) else ("In Process" if (im["sho"] > 0 or om["sho"] > 0) else "Yet to Start")
            latest_ch_date = str(data["ch_date_max"]) if data["ch_date_max"] else "-"

            if im["qty_req"] > 0 or im["sho"] > 0 or data["ch_qty"] > 0:
                compiled_summary.append({
                    "mo": mo, "base_product": data["base_product"], "component": "IM",
                    "qty_req": math.ceil(im["qty_req"]), "sho_qty": math.ceil(im["sho"]), "sho_date": im["sho_d"],
                    "tb_qty": math.ceil(im["tb"]), "tb_date": im["tb_d"],
                    "ch_qty": math.ceil(data["ch_qty"]), "ch_date": latest_ch_date, "status": status
                })
            
            if om["qty_req"] > 0 or om["sho"] > 0:
                compiled_summary.append({
                    "mo": mo, "base_product": data["base_product"], "component": "OM",
                    "qty_req": math.ceil(om["qty_req"]), "sho_qty": math.ceil(om["sho"]), "sho_date": om["sho_d"],
                    "tb_qty": math.ceil(om["tb"]), "tb_date": om["tb_d"],
                    "ch_qty": math.ceil(data["ch_qty"]), "ch_date": latest_ch_date, "status": status
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
    if not search_group:
        return {"status": "error", "message": "Invalid MO"}
        
    jw_sho_agg, jw_tb_agg, ch_agg = {}, {}, {}

    for r in GLOBAL_RAW_RECORDS["jw_data"]:
        if r["mo_group"] == search_group:
            v_name = r["variant"]
            
            if r["sho_qty"] > 0:
                if v_name not in jw_sho_agg: jw_sho_agg[v_name] = {"qty": 0, "dates": []}
                jw_sho_agg[v_name]["qty"] += r["sho_qty"]
                if r["sho_date"]: jw_sho_agg[v_name]["dates"].append(r["sho_date"])
                
            if r["tb_qty"] > 0:
                if v_name not in jw_tb_agg: jw_tb_agg[v_name] = {"qty": 0, "dates": []}
                jw_tb_agg[v_name]["qty"] += r["tb_qty"]
                if r["tb_date"]: jw_tb_agg[v_name]["dates"].append(r["tb_date"])

    for r in GLOBAL_RAW_RECORDS["ch_data"]:
        if r["mo_group"] == search_group:
            v_name = r["variant"]
            if r["ch_qty"] > 0:
                if v_name not in ch_agg: ch_agg[v_name] = {"qty": 0, "dates": []}
                ch_agg[v_name]["qty"] += r["ch_qty"]
                if r["ch_date"]: ch_agg[v_name]["dates"].append(r["ch_date"])

    rows = []

    for v_name, data in jw_sho_agg.items():
        in_d = str(min(data["dates"])) if data["dates"] else "-"
        rows.append({
            "mo_ref": search_group, "department": "SHO Department", 
            "variant": v_name, "in_date": in_d, "out_date": "-", 
            "qty": math.ceil(data["qty"]), "status": "Allocated"
        })
        
    for v_name, data in jw_tb_agg.items():
        out_d = str(max(data["dates"])) if data["dates"] else "-"
        rows.append({
            "mo_ref": search_group, "department": "Transit Buffer", 
            "variant": v_name, "in_date": "-", "out_date": out_d, 
            "qty": math.ceil(data["qty"]), "status": "In Transit"
        })

    for v_name, data in ch_agg.items():
        in_d = str(min(data["dates"])) if data["dates"] else "-"
        out_d = str(max(data["dates"])) if data["dates"] else "-"
        rows.append({
            "mo_ref": search_group, "department": "Channel Section", 
            "variant": v_name, "in_date": in_d, "out_date": out_d, 
            "qty": math.ceil(data["qty"]), "status": "Completed"
        })

    return {"status": "success", "data": {"mo": search_group, "rows": rows}}
