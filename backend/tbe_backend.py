import os
import time
import pandas as pd
from fastapi import APIRouter, HTTPException
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Define the router that your main application is looking to import
router = APIRouter()

# Fetch the Excel URL from .env
RINGWT_TRANSITBUFFER_URL = os.getenv("RINGWT_TRANSITBUFFERE_URL")

# ---------------------------------------------------------
# CACHING SYSTEM FOR 22MB FILE
# ---------------------------------------------------------
CACHED_DF = None
LAST_CACHE_TIME = 0
CACHE_TTL_SECONDS = 600  # 10 minutes cache lifetime

# ---------------------------------------------------------
# HELPER FUNCTIONS
# ---------------------------------------------------------
def clean_channel(ch_string):
    if pd.isna(ch_string):
        return None
    match = pd.Series(str(ch_string).upper()).str.extract(r'(\d+)')[0].values
    if len(match) > 0 and pd.notna(match[0]):
        return str(match[0])
    return str(ch_string)

def extract_family(type_string):
    if pd.isna(type_string):
        return ""
    match = pd.Series(str(type_string)).str.extract(r'(\d{3,})')[0].values
    if len(match) > 0 and pd.notna(match[0]):
        return str(match[0])
    return str(type_string)

def fetch_and_process_excel():
    """Downloads and processes the 22MB spreadsheet file into memory."""
    if not RINGWT_TRANSITBUFFER_URL:
        raise ValueError("RINGWT_TRANSITBUFFERE_URL is missing in environment variables.")
        
    print("Downloading and processing 22MB Excel file... This may take a moment.")
    
    # Load Data
    df = pd.read_excel(RINGWT_TRANSITBUFFER_URL)
    df.columns = df.columns.str.strip() 
    
    # Standardize Columns
    df['Date'] = pd.to_datetime(df['Date'], errors='coerce')
    df = df.dropna(subset=['Date']) 
    
    df['Clean_Channel'] = df['Ch#'].apply(clean_channel)
    df['Base_Family'] = df['TYPE'].apply(extract_family)
    
    # DATE PROXIMITY LOGIC (Groups production intervals automatically)
    df = df.sort_values(by=['Clean_Channel', 'Base_Family', 'Date'])
    df['Date_Diff'] = df.groupby(['Clean_Channel', 'Base_Family'])['Date'].diff().dt.days
    df['New_Run_Flag'] = (df['Date_Diff'].fillna(0) > 10).astype(int)
    df['Run_ID'] = df.groupby(['Clean_Channel', 'Base_Family'])['New_Run_Flag'].cumsum()
    
    # GENERATE PRIMARY KEY MO
    df['Generated_MO'] = "MO-CH" + df['Clean_Channel'].astype(str) + "-" + df['Base_Family'].astype(str) + "-R" + (df['Run_ID'] + 1).astype(str)
    
    # Clean up NaNs for clean JSON transmission
    df = df.fillna(0)
    print("Processing complete. Data cached successfully.")
    return df

def get_processed_tbe_data(force_refresh=False):
    """Returns cached data if valid, otherwise updates cache with fresh data."""
    global CACHED_DF, LAST_CACHE_TIME
    
    current_time = time.time()
    
    if CACHED_DF is not None and not force_refresh and (current_time - LAST_CACHE_TIME < CACHE_TTL_SECONDS):
        return CACHED_DF
        
    try:
        df = fetch_and_process_excel()
        CACHED_DF = df
        LAST_CACHE_TIME = current_time
        return df
    except Exception as e:
        print(f"Error processing TBE data: {e}")
        if CACHED_DF is not None:
            return CACHED_DF
        return pd.DataFrame()

# ---------------------------------------------------------
# ENDPOINT: FORCE CACHE REFRESH
# ---------------------------------------------------------
@router.get("/refresh_tbe")
def refresh_cache():
    df = get_processed_tbe_data(force_refresh=True)
    if not df.empty:
        return {"status": "success", "message": "Cache updated successfully."}
    return {"status": "error", "message": "Failed to update cache."}

# ---------------------------------------------------------
# ENDPOINT 1: SUMMARY DASHBOARD (ALL MOs)
# ---------------------------------------------------------
@router.get("/tbe_all_mos")
def get_tbe_summary():
    df = get_processed_tbe_data()
    
    if df.empty:
        return {"status": "error", "message": "Failed to fetch or parse TBE pipeline."}

    agg_funcs = {
        'Clean_Channel': 'first',
        'Base_Family': 'first',
        'TYPE': 'first',
        'No Of Rings': 'sum',
        'Net Wt': 'sum',
        'Date': ['min', 'max']
    }
    
    grouped = df.groupby('Generated_MO').agg(agg_funcs).reset_index()
    grouped.columns = ['mo', 'channel', 'family', 'component', 'total_rings', 'total_net_wt', 'first_scan', 'last_scan']
    
    payload = []
    for _, row in grouped.iterrows():
        if row['total_rings'] <= 0:
            continue
            
        payload.append({
            "mo": row['mo'],
            "channel": row['channel'],
            "base_product": row['family'],
            "component_type": row['component'],
            "total_rings": int(row['total_rings']),
            "total_net_weight": round(float(row['total_net_wt']), 2),
            "in_date": row['first_scan'].strftime('%Y-%m-%d') if pd.notna(row['first_scan']) and row['first_scan'] != 0 else '-',
            "out_date": row['last_scan'].strftime('%Y-%m-%d') if pd.notna(row['last_scan']) and row['last_scan'] != 0 else '-',
            "status": "completed"
        })
        
    payload = sorted(payload, key=lambda x: (x['channel'], x['base_product']))
    return {"status": "success", "data": payload}

# ---------------------------------------------------------
# ENDPOINT 2: DETAILED MO DRILLDOWN
# ---------------------------------------------------------
@router.get("/tbe_report/{mo_id}")
def get_tbe_detail(mo_id: str):
    df = get_processed_tbe_data()
    
    if df.empty:
        return {"status": "error", "message": "Pipeline unavailable."}
        
    filtered_df = df[df['Generated_MO'] == mo_id.strip()]

    rows = []
    for _, row in filtered_df.iterrows():
        rows.append({
            "department": f"Channel {row['Clean_Channel']}",
            "product": row['TYPE'] if row['TYPE'] != 0 else '-',
            "date": row['Date'].strftime('%Y-%m-%d') if row['Date'] != 0 else '-',
            "shift": row['Shift'] if row['Shift'] != 0 else '-',
            "gross_weight": float(row['Gr Wt']) if row['Gr Wt'] != 0 else 0,
            "net_weight": float(row['Net Wt']) if row['Net Wt'] != 0 else 0,
            "ring_weight": float(row['Ring Wt']) if row['Ring Wt'] != 0 else 0,
            "rings": int(row['No Of Rings']) if row['No Of Rings'] != 0 else 0,
            "status": "completed" if row['No Of Rings'] != 0 else "pending"
        })

    return {
        "status": "success",
        "data": {
            "mo": mo_id,
            "rows": rows
        }
    }
