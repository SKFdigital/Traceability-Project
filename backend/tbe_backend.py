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

# =========================================================
# GLOBAL CACHE
# =========================================================
MASTER_CACHE = []
FLOW_CACHE = {}
LAST_REFRESH = None
IS_UPDATING = False
CACHE_DURATION_MINUTES = 5

# =========================================================
# HELPERS
# =========================================================
def clean_mo(value):
    if pd.isna(value):
        return None

    val = (
        str(value)
        .strip()
        .upper()
        .replace(" ", "")
        .replace(".0", "")
    )

    if val in ["NAN", "-", "...", ""] or len(val) < 4:
        return None

    return val


def normalize_text(value):
    if pd.isna(value):
        return ""

    return (
        str(value)
        .strip()
        .upper()
        .replace("-", " ")
        .replace("  ", " ")
    )


def clean_channel(value):
    if pd.isna(value):
        return ""

    return (
        str(value)
        .strip()
        .upper()
        .replace(" ", "")
    )


def clean_nan(value):
    try:
        if pd.isna(value):
            return 0.0

        val = str(value).strip().lower()

        if val in ["nan", "-", "...", ""]:
            return 0.0

        f = float(value)

        if math.isnan(f):
            return 0.0

        return f

    except:
        return 0.0


def parse_date_safe(value):
    try:
        if pd.isna(value):
            return None

        val = str(value).strip().lower()

        if val in ["nan", "nat", "", "-"]:
            return None

        parsed = pd.to_datetime(
            value,
            errors="coerce",
            dayfirst=True
        )

        if pd.isna(parsed):
            return None

        return parsed.date()

    except:
        return None


# =========================================================
# FAMILY EXTRACTION
# =========================================================
def extract_family(product_name):
    """
    Examples:
    6204 ZZ IM -> 6204
    6305 OPEN OM -> 6305
    """

    text = normalize_text(product_name)

    match = re.search(r"\b(\d{4,5})\b", text)

    if match:
        return match.group(1)

    return text


def extract_component(product_name):
    text = normalize_text(product_name)

    if "IM" in text or "IR" in text:
        return "IM"

    if "OM" in text or "OR" in text:
        return "OM"

    return "ASSEMBLY"


# =========================================================
# EXCEL LOADER
# =========================================================
def download_excel(url):
    response = requests.get(url)

    if response.status_code != 200:
        raise Exception(f"Failed downloading excel from {url}")

    return io.BytesIO(response.content)


def load_excel_sheets(url):
    try:
        excel_data = download_excel(url)

        xls = pd.ExcelFile(excel_data)

        sheets = {}

        for sheet in xls.sheet_names:
            try:
                df = pd.read_excel(xls, sheet_name=sheet)

                df.columns = [
                    str(c).strip().lower()
                    for c in df.columns
                ]

                sheets[sheet] = df

            except Exception as e:
                print(f"Error reading sheet [{sheet}] : {str(e)}")

        return sheets

    except Exception as e:
        print(f"Failed loading workbook {url} : {str(e)}")
        return {}


# =========================================================
# MAIN ENGINE
# =========================================================
def process_tbe_dashboard_data():
    global MASTER_CACHE
    global FLOW_CACHE
    global LAST_REFRESH
    global IS_UPDATING

    if IS_UPDATING:
        return

    IS_UPDATING = True

    print(f"[{datetime.now()}] TBE ENGINE STARTED")

    try:

        # =====================================================
        # LOAD FILES
        # =====================================================
        transit_sheets = load_excel_sheets(
            settings.RINGWT_TRANSITBUFFER_URL
        )

        trb_sheets = load_excel_sheets(
            settings.TRB_MASTER_URL
        )

        dgbb_sheets = load_excel_sheets(
            settings.DGBB_MASTER_URL
        )

        # =====================================================
        # STORAGE
        # =====================================================
        summary_aggregation = {}
        flow_records = {}

        # channel + family -> timeline rows
        channel_family_map = {}

        # =====================================================
        # STEP 1 : PROCESS CHANNEL FILES
        # =====================================================
        all_channel_sheets = {
            **trb_sheets,
            **dgbb_sheets
        }

        variant_max_tracker = {}

        for sheet_name, df in all_channel_sheets.items():

            mo_col = next(
                (c for c in ["mo", "mo#"] if c in df.columns),
                None
            )

            type_col = next(
                (
                    c
                    for c in [
                        "type",
                        "product",
                        "product variant"
                    ]
                    if c in df.columns
                ),
                None
            )

            ch_col = next(
                (
                    c
                    for c in [
                        "channel",
                        "ch#",
                        "channel no"
                    ]
                    if c in df.columns
                ),
                None
            )

            if not mo_col or not type_col:
                continue

            for _, row in df.iterrows():

                raw_mo = clean_mo(
                    row.get(mo_col)
                )

                if not raw_mo:
                    continue

                product = normalize_text(
                    row.get(type_col)
                )

                family = extract_family(product)

                component = extract_component(product)

                channel = clean_channel(
                    row.get(ch_col)
                )

                production = clean_nan(
                    row.get("production")
                )

                cumulative = clean_nan(
                    row.get("cumulative production")
                )

                row_date = parse_date_safe(
                    row.get("date")
                )

                # -----------------------------------------
                # FLOW RECORDS
                # -----------------------------------------
                if raw_mo not in flow_records:
                    flow_records[raw_mo] = {
                        "mo": raw_mo,
                        "timeline": []
                    }

                flow_records[raw_mo]["timeline"].append({
                    "department": sheet_name,
                    "product": product,
                    "channel": channel,
                    "date": str(row_date) if row_date else "-",
                    "production": production,
                    "cumulative": cumulative
                })

                # -----------------------------------------
                # CHANNEL FAMILY MAP
                # -----------------------------------------
                if channel and family and row_date:

                    map_key = (channel, family)

                    if map_key not in channel_family_map:
                        channel_family_map[map_key] = []

                    channel_family_map[map_key].append({
                        "mo": raw_mo,
                        "family": family,
                        "product": product,
                        "component": component,
                        "date": row_date
                    })

                # -----------------------------------------
                # MAX CUMULATIVE TRACKER
                # -----------------------------------------
                v_key = (
                    raw_mo,
                    family,
                    product
                )

                if v_key not in variant_max_tracker:
                    variant_max_tracker[v_key] = {
                        "max_cum": 0.0,
                        "min_date": None,
                        "max_date": None
                    }

                v_meta = variant_max_tracker[v_key]

                if cumulative > v_meta["max_cum"]:
                    v_meta["max_cum"] = cumulative

                if row_date:
                    if (
                        not v_meta["min_date"]
                        or row_date < v_meta["min_date"]
                    ):
                        v_meta["min_date"] = row_date

                    if (
                        not v_meta["max_date"]
                        or row_date > v_meta["max_date"]
                    ):
                        v_meta["max_date"] = row_date

        # =====================================================
        # STEP 2 : FAMILY LEVEL CHANNEL TOTALS
        # =====================================================
        family_channel_totals = {}

        for (
            raw_mo,
            family,
            product
        ), v_meta in variant_max_tracker.items():

            component = extract_component(product)

            f_key = (
                raw_mo,
                family,
                component
            )

            if f_key not in family_channel_totals:
                family_channel_totals[f_key] = {
                    "mo": raw_mo,
                    "family": family,
                    "component": component,

                    "ch_qty": 0.0,
                    "ch_in": None,
                    "ch_out": None,

                    "sho_qty": 0.0,
                    "tb_qty": 0.0,
                    "tb_out": None
                }

            f_meta = family_channel_totals[f_key]

            f_meta["ch_qty"] += v_meta["max_cum"]

            if v_meta["min_date"]:
                if (
                    not f_meta["ch_in"]
                    or v_meta["min_date"] < f_meta["ch_in"]
                ):
                    f_meta["ch_in"] = v_meta["min_date"]

            if v_meta["max_date"]:
                if (
                    not f_meta["ch_out"]
                    or v_meta["max_date"] > f_meta["ch_out"]
                ):
                    f_meta["ch_out"] = v_meta["max_date"]

        # =====================================================
        # STEP 3 : MATCH TRANSIT BUFFER
        # =====================================================
        for sheet_name, df in transit_sheets.items():

            ch_col = next(
                (
                    c
                    for c in [
                        "channel",
                        "ch#",
                        "ch"
                    ]
                    if c in df.columns
                ),
                None
            )

            type_col = next(
                (
                    c
                    for c in [
                        "type",
                        "product"
                    ]
                    if c in df.columns
                ),
                None
            )

            qty_col = next(
                (
                    c
                    for c in [
                        "no of rings",
                        "qty"
                    ]
                    if c in df.columns
                ),
                None
            )

            date_col = "date" if "date" in df.columns else None

            if not ch_col or not type_col or not qty_col:
                continue

            for _, row in df.iterrows():

                tb_channel = clean_channel(
                    row.get(ch_col)
                )

                tb_product = normalize_text(
                    row.get(type_col)
                )

                tb_family = extract_family(tb_product)

                tb_component = extract_component(tb_product)

                tb_qty = clean_nan(
                    row.get(qty_col)
                )

                tb_date = parse_date_safe(
                    row.get(date_col)
                )

                if not tb_channel:
                    continue

                if tb_qty <= 0:
                    continue

                # -----------------------------------------
                # MATCH CHANNEL + FAMILY
                # -----------------------------------------
                possible_matches = channel_family_map.get(
                    (tb_channel, tb_family),
                    []
                )

                if not possible_matches:
                    continue

                # -----------------------------------------
                # FILTER COMPONENT
                # -----------------------------------------
                possible_matches = [
                    x
                    for x in possible_matches
                    if x["component"] == tb_component
                ]

                if not possible_matches:
                    continue

                # -----------------------------------------
                # CLOSEST DATE MATCH
                # -----------------------------------------
                if tb_date:
                    best_match = min(
                        possible_matches,
                        key=lambda x: abs(
                            (x["date"] - tb_date).days
                        )
                    )
                else:
                    best_match = possible_matches[-1]

                agg_key = (
                    best_match["mo"],
                    best_match["family"],
                    best_match["component"]
                )

                if agg_key not in family_channel_totals:
                    continue

                family_channel_totals[agg_key]["sho_qty"] += tb_qty
                family_channel_totals[agg_key]["tb_qty"] += tb_qty

                if tb_date:
                    current_tb_out = family_channel_totals[
                        agg_key
                    ]["tb_out"]

                    if (
                        not current_tb_out
                        or tb_date > current_tb_out
                    ):
                        family_channel_totals[
                            agg_key
                        ]["tb_out"] = tb_date

        # =====================================================
        # STEP 4 : FINAL OUTPUT
        # =====================================================
        compiled_summary = []

        for (
            raw_mo,
            family,
            component
        ), meta in family_channel_totals.items():

            # STATUS
            if meta["sho_qty"] == 0 and meta["ch_qty"] == 0:
                status = "Yet To Start"

            elif meta["ch_qty"] >= meta["sho_qty"]:
                status = "Completed"

            else:
                status = "In Process"

            compiled_summary.append({
                "mo": raw_mo,

                "final_variant": family,

                "component_type": component,

                "qty_req": int(meta["sho_qty"]),

                "sho_qty": meta["sho_qty"],
                "sho_in": "-",

                "tb_qty": meta["tb_qty"],
                "tb_out": (
                    str(meta["tb_out"])
                    if meta["tb_out"]
                    else "-"
                ),

                "ch_qty": meta["ch_qty"],

                "ch_in": (
                    str(meta["ch_in"])
                    if meta["ch_in"]
                    else "-"
                ),

                "ch_out": (
                    str(meta["ch_out"])
                    if meta["ch_out"]
                    else "-"
                ),

                "status": status
            })

        # SORTING
        compiled_summary.sort(
            key=lambda x: (
                x["mo"],
                x["final_variant"],
                x["component_type"]
            )
        )

        MASTER_CACHE = compiled_summary
        FLOW_CACHE = flow_records
        LAST_REFRESH = datetime.now()

        print(f"[{datetime.now()}] TBE CACHE READY")

    except Exception as e:
        print(f"CRITICAL TBE ENGINE ERROR : {str(e)}")

    finally:
        IS_UPDATING = False


# =========================================================
# BACKGROUND REFRESH
# =========================================================
def background_refresh_loop():

    process_tbe_dashboard_data()

    while True:
        time.sleep(CACHE_DURATION_MINUTES * 60)
        process_tbe_dashboard_data()


threading.Thread(
    target=background_refresh_loop,
    daemon=True
).start()

# =========================================================
# ROUTES
# =========================================================
@router.get("/traceability_all_mos")
def get_all_mos():

    if not LAST_REFRESH and not MASTER_CACHE:
        return {
            "status": "initializing",
            "message": "TBE cache warming up...",
            "data": []
        }

    return {
        "status": "success",
        "last_updated": str(LAST_REFRESH),
        "data": MASTER_CACHE
    }


@router.get("/traceability_report/{mo}")
def get_flow(mo: str):

    search_mo = clean_mo(mo)

    if search_mo in FLOW_CACHE:
        return {
            "status": "success",
            "last_updated": str(LAST_REFRESH),
            "data": FLOW_CACHE[search_mo]
        }

    raise HTTPException(
        status_code=404,
        detail=f"No flow found for MO {mo}"
    )
