from fastapi import APIRouter, HTTPException
import pandas as pd
import requests
import io
import threading
import time
import re
import math
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

    if val in ["", "-", "...", "NAN"]:
        return None

    return val


def normalize_text(value):

    if pd.isna(value):
        return ""

    return str(value).strip().upper()


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

        if (
            pd.isna(value)
            or str(value).strip().lower()
            in ["nan", "-", "...", ""]
        ):
            return 0.0

        val = float(value)

        if math.isnan(val):
            return 0.0

        return val

    except:
        return 0.0


def parse_date_safe(value):

    try:

        if (
            pd.isna(value)
            or str(value).strip().lower()
            in ["nan", "nat", "", "-"]
        ):
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

    text = normalize_text(product_name)

    # remove IM / OM
    text = re.sub(r"^(IM|OM)", "", text)

    # extract first family
    match = re.search(r"(\d{3,5})", text)

    if match:
        return match.group(1)

    return None


def get_component(product_name):

    text = normalize_text(product_name)

    if text.startswith("IM"):
        return "IM"

    if text.startswith("OM"):
        return "OM"

    return "NA"


# =========================================================
# EXCEL HELPERS
# =========================================================
def download_excel(url):

    response = requests.get(url)

    if response.status_code != 200:
        raise Exception(
            f"Failed downloading excel from {url}"
        )

    return io.BytesIO(response.content)


def load_excel_sheets(url):

    try:

        excel_data = download_excel(url)

        xls = pd.ExcelFile(excel_data)

        sheets = {}

        for sheet in xls.sheet_names:

            try:

                df = pd.read_excel(
                    xls,
                    sheet_name=sheet
                )

                df.columns = [
                    str(c).strip().lower()
                    for c in df.columns
                ]

                sheets[sheet] = df

            except Exception as e:

                print(
                    f"Error reading [{sheet}] : {e}"
                )

        return sheets

    except Exception as e:

        print(
            f"Workbook load failed : {e}"
        )

        return {}


# =========================================================
# MAIN ENGINE
# =========================================================
def process_tbe_dashboard():

    global MASTER_CACHE
    global FLOW_CACHE
    global LAST_REFRESH
    global IS_UPDATING

    if IS_UPDATING:
        return

    IS_UPDATING = True

    try:

        trb_sheets = load_excel_sheets(
            settings.TRB_MASTER_URL
        )

        dgbb_sheets = load_excel_sheets(
            settings.DGBB_MASTER_URL
        )

        tb_sheets = load_excel_sheets(
            settings.RINGWT_TRANSITBUFFER_URL
        )

        summary_aggregation = {}

        flow_cache = {}

        channel_rows = []

        # =====================================================
        # STEP 1 : CHANNEL PROCESSING
        # =====================================================
        all_channels = {
            **trb_sheets,
            **dgbb_sheets
        }

        for sheet_name, df in all_channels.items():

            mo_col = (
                "mo"
                if "mo" in df.columns
                else "mo#"
            )

            type_col = None

            for c in [
                "type",
                "product",
                "product variant"
            ]:
                if c in df.columns:
                    type_col = c
                    break

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

                if not family:
                    continue

                component = get_component(product)

                channel = clean_channel(
                    row.get("channel")
                    or row.get("ch#")
                    or row.get("channel no")
                )

                row_date = parse_date_safe(
                    row.get("date")
                )

                production = clean_nan(
                    row.get("production")
                )

                cumulative = clean_nan(
                    row.get("cumulative production")
                )

                agg_key = (
                    raw_mo,
                    family,
                    component
                )

                if agg_key not in summary_aggregation:

                    summary_aggregation[agg_key] = {

                        "mo": raw_mo,

                        "family": family,

                        "component": component,

                        "sho_qty": 0.0,

                        "tb_qty": 0.0,

                        "tb_out": None,

                        "ch_qty": 0.0,

                        "ch_in": None,

                        "ch_out": None
                    }

                agg = summary_aggregation[agg_key]

                # IMPORTANT
                # family total logic
                if cumulative > agg["ch_qty"]:
                    agg["ch_qty"] = cumulative

                if row_date:

                    if (
                        agg["ch_in"] is None
                        or row_date < agg["ch_in"]
                    ):
                        agg["ch_in"] = row_date

                    if (
                        agg["ch_out"] is None
                        or row_date > agg["ch_out"]
                    ):
                        agg["ch_out"] = row_date

                channel_rows.append({

                    "mo": raw_mo,

                    "family": family,

                    "component": component,

                    "channel": channel,

                    "date": row_date,

                    "production": production,

                    "cumulative": cumulative,

                    "product": product,

                    "department": sheet_name
                })

                if raw_mo not in flow_cache:

                    flow_cache[raw_mo] = {
                        "mo": raw_mo,
                        "timeline": []
                    }

                flow_cache[raw_mo]["timeline"].append({

                    "department": sheet_name,

                    "product": product,

                    "channel": channel,

                    "date": (
                        str(row_date)
                        if row_date
                        else "-"
                    ),

                    "production": production,

                    "cumulative": cumulative
                })

        # =====================================================
        # STEP 2 : TRANSIT BUFFER MAPPING
        # =====================================================
        for sheet_name, df in tb_sheets.items():

            ch_col = None

            for c in [
                "ch#",
                "channel",
                "ch"
            ]:
                if c in df.columns:
                    ch_col = c
                    break

            if not ch_col:
                continue

            type_col = (
                "type"
                if "type" in df.columns
                else None
            )

            qty_col = (
                "no of rings"
                if "no of rings" in df.columns
                else None
            )

            if not type_col or not qty_col:
                continue

            for _, row in df.iterrows():

                tb_channel = clean_channel(
                    row.get(ch_col)
                )

                tb_product = normalize_text(
                    row.get(type_col)
                )

                tb_family = extract_family(
                    tb_product
                )

                if not tb_family:
                    continue

                tb_component = get_component(
                    tb_product
                )

                tb_qty = clean_nan(
                    row.get(qty_col)
                )

                tb_date = parse_date_safe(
                    row.get("date")
                )

                if tb_qty <= 0:
                    continue

                # closest matching
                possible_matches = [

                    x for x in channel_rows

                    if (
                        x["channel"] == tb_channel
                        and
                        x["family"] == tb_family
                        and
                        x["component"] == tb_component
                    )
                ]

                if not possible_matches:
                    continue

                if tb_date:

                    best_match = min(

                        possible_matches,

                        key=lambda x:
                        abs(
                            (
                                x["date"]
                                - tb_date
                            ).days
                        )
                        if x["date"]
                        else 99999
                    )

                else:

                    best_match = possible_matches[-1]

                agg_key = (
                    best_match["mo"],
                    best_match["family"],
                    best_match["component"]
                )

                if agg_key not in summary_aggregation:
                    continue

                agg = summary_aggregation[agg_key]

                agg["tb_qty"] += tb_qty

                if tb_date:

                    if (
                        agg["tb_out"] is None
                        or tb_date > agg["tb_out"]
                    ):
                        agg["tb_out"] = tb_date

        # =====================================================
        # STEP 3 : FINAL SUMMARY
        # =====================================================
        compiled_summary = []

        for (
            raw_mo,
            family,
            component
        ), agg in summary_aggregation.items():

            if not family:
                continue

            # remove empty junk rows
            if (
                agg["ch_qty"] <= 0
                and agg["tb_qty"] <= 0
            ):
                continue

            if agg["ch_qty"] <= 0:
                status = "Yet To Start"

            elif agg["tb_qty"] >= agg["ch_qty"]:
                status = "Completed"

            else:
                status = "In Process"

            compiled_summary.append({

                "mo": raw_mo,

                "final_variant": family,

                "component_type": component,

                "qty_req": int(agg["tb_qty"]),

                "sho_qty": int(agg["tb_qty"]),

                "sho_in": "-",

                "tb_qty": int(agg["tb_qty"]),

                "tb_out": (
                    str(agg["tb_out"])
                    if agg["tb_out"]
                    else "-"
                ),

                "ch_qty": int(agg["ch_qty"]),

                "ch_in": (
                    str(agg["ch_in"])
                    if agg["ch_in"]
                    else "-"
                ),

                "ch_out": (
                    str(agg["ch_out"])
                    if agg["ch_out"]
                    else "-"
                ),

                "status": status
            })

        compiled_summary.sort(

            key=lambda x: (

                x["mo"],

                x["final_variant"],

                x["component_type"]
            )
        )

        MASTER_CACHE = compiled_summary

        FLOW_CACHE = flow_cache

        LAST_REFRESH = datetime.now()

        print(
            f"[{datetime.now()}] "
            f"TBE CACHE REFRESHED"
        )

    except Exception as e:

        print(
            f"TBE ENGINE ERROR : {e}"
        )

    finally:

        IS_UPDATING = False


# =========================================================
# BACKGROUND THREAD
# =========================================================
def background_refresh_loop():

    process_tbe_dashboard()

    while True:

        time.sleep(
            CACHE_DURATION_MINUTES * 60
        )

        process_tbe_dashboard()


threading.Thread(
    target=background_refresh_loop,
    daemon=True
).start()


# =========================================================
# API
# =========================================================
@router.get("/traceability_all_mos")
def get_all_mos():

    return {

        "status": "success",

        "last_updated": str(LAST_REFRESH),

        "data": MASTER_CACHE
    }


@router.get("/traceability_report/{mo}")
def get_flow(mo: str):

    clean = clean_mo(mo)

    if clean in FLOW_CACHE:

        return {

            "status": "success",

            "last_updated": str(LAST_REFRESH),

            "data": FLOW_CACHE[clean]
        }

    raise HTTPException(
        status_code=404,
        detail="MO not found"
    )
