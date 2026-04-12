import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import warnings
import requests
from streamlit_searchbox import st_searchbox
from modules.market_math import fetch_live_data_and_stage
import datetime

warnings.filterwarnings('ignore')

st.set_page_config(page_title="Paper Trading", page_icon="👀", layout="wide")

SPREADSHEET = "https://docs.google.com/spreadsheets/d/18ci-lXIJAhb-T96DZ1bL5sEKVmishPTBItIMaACBRJw/edit?gid=0#gid=0"

if "show_add_panel" not in st.session_state:
    st.session_state.show_add_panel = False

# ==========================================
# LIVE API SEARCH FUNCTION
# ==========================================
def search_yahoo_finance(searchterm: str):
    if not searchterm or len(searchterm) < 2:
        return []
    
    url = f"https://query2.finance.yahoo.com/v1/finance/search?q={searchterm}&quotesCount=10&newsCount=0"
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
    
    try:
        response = requests.get(url, headers=headers)
        data = response.json()
        quotes = data.get('quotes', [])
        
        results = []
        for q in quotes:
            symbol = q.get('symbol', '')
            name = q.get('shortname', symbol)
            if symbol.endswith('.NS') or symbol.endswith('.BO'):
                results.append((f"{name} ({symbol})", symbol))
                
        if not results:
            results.append((f"Search globally for: {searchterm.upper()}", searchterm.upper()))
            
        return results
    except Exception:
        return []

# ==========================================
# RENDER LOGIC WITH AGGREGATES & DELETE
# ==========================================
def analyze_and_render_watchlists(watchlist_df, conn):
    required_cols = ['List Name', 'Instrument', 'Date Added', 'Price Added']
    if not all(col in watchlist_df.columns for col in required_cols):
        st.error(f"Watchlist sheet is missing columns. It must exactly have: {', '.join(required_cols)}")
        return

    list_names = [name for name in watchlist_df['List Name'].unique() if pd.notnull(name) and str(name).strip() != '']
    if len(list_names) == 0:
        return

    # 1. Fetch ALL data first for Global Aggregates
    all_raw_tickers = [str(t).strip() for t in watchlist_df['Instrument'].tolist() if pd.notnull(t)]
    all_tickers = [t + ".NS" if not (t.endswith(".NS") or t.endswith(".BO")) else t for t in all_raw_tickers]
    
    with st.spinner("Fetching live market data for all lists..."):
        all_results, _ = fetch_live_data_and_stage(all_tickers)
    
    if not all_results:
        st.warning("Could not fetch live market data.")
        return

    # Build Master Analysis DF
    live_df = pd.DataFrame(all_results)
    
    def clean_price(val):
        try: return float(str(val).replace(',', '').strip())
        except: return 0.0

    master_df = pd.merge(watchlist_df, live_df, left_on='Instrument', right_on='Ticker
