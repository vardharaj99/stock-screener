import streamlit as st
import pandas as pd
from googleapiclient.discovery import build
from modules.google_auth import authenticate_user, get_user_spreadsheet_id
from modules.market_math import fetch_live_data_and_stage
from streamlit_searchbox import st_searchbox
import requests
import warnings
import datetime

warnings.filterwarnings('ignore')

# Set page config for high screen real estate
st.set_page_config(page_title="Watchlists", page_icon="👀", layout="wide")

# 1. ENFORCE PRIVATE AUTHENTICATION
creds = authenticate_user()
ss_id = get_user_spreadsheet_id(creds)
service = build('sheets', 'v4', credentials=creds)

if "show_add_panel" not in st.session_state:
    st.session_state.show_add_panel = False

# ==========================================
# API HELPER FUNCTIONS (Direct Google API)
# ==========================================
def get_sheet_data(spreadsheet_id, range_name):
    """Reads data from the private spreadsheet."""
    try:
        result = service.spreadsheets().values().get(spreadsheetId=spreadsheet_id, range=range_name).execute()
        values = result.get('values', [])
        if not values or len(values) < 1:
            return pd.DataFrame(columns=["List Name", "Instrument", "Date Added", "Price Added"])
        return pd.DataFrame(values[1:], columns=values[0])
    except Exception as e:
        st.error(f"Error reading from your Google Sheet: {e}")
        return pd.DataFrame(columns=["List Name", "Instrument", "Date Added", "Price Added"])

def update_sheet_full(spreadsheet_id, range_name, df):
    """Overwrites the sheet (used for Deletions)."""
    service.spreadsheets().values().clear(spreadsheetId=spreadsheet_id, range=range_name).execute()
    body = {'values': [df.columns.tolist()] + df.values.tolist()}
    service.spreadsheets().values().update(
        spreadsheetId=spreadsheet_id, range=range_name,
        valueInputOption="RAW", body=body).execute()

# ==========================================
# SEARCH & RENDER LOGIC
# ==========================================
def search_yahoo_finance(searchterm: str):
    if not searchterm or len(searchterm) < 2: return []
    url = f"https://query2.finance.yahoo.com/v1/finance/search?q={searchterm}&quotesCount=10"
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        resp = requests.get(url, headers=headers).json()
        return [(f"{q.get('shortname')} ({q.get('symbol')})", q.get('symbol')) 
                for q in resp.get('quotes', []) if '.NS' in q.get('symbol') or '.BO' in q.get('symbol')]
    except: return []

def analyze_and_render_watchlists(watchlist_df, spreadsheet_id):
    list_names = [n for n in watchlist_df['List Name'].unique() if n]
    if not list_names:
        st.info("No watchlists found. Use the 'Add Stocks' button to create your first list.")
        return

    tabs = st.tabs(list_names)
    for tab, current_list in zip(tabs, list_names):
        with tab:
            df = watchlist_df[watchlist_df['List Name'] == current_list].copy()
            tickers = [t if ('.NS' in t or '.BO' in t) else f"{t}.NS" for t in df['Instrument']]
            
            with st.spinner(f"Updating {current_list}..."):
                results, _ = fetch_live_data_and_stage(tickers)
            
            if results:
                analysis_df = pd.DataFrame(results)
                merged_df = pd.merge(df, analysis_df, left_on='Instrument', right_on='Ticker', how='left')
                
                # Math Logic
                merged_df['Price Added'] = pd.to_numeric(merged_df['Price Added'], errors='coerce').fillna(0)
                merged_df['Qty'] = merged_df['Price Added'].apply(lambda x: int(round(100000 / x)) if x > 0 else 0)
                merged_df['Invested'] = 100000.0
                merged_df['Cur. Val'] = merged_df['Live Price'] * merged_df['Qty']
                merged_df['Hypo. P&L'] = merged_df['Cur. Val'] - merged_df['Invested']
                merged_df['Hypo. Net Chg (%)'] = (merged_df['Hypo. P&L'] / 1000).round(2)
                
                def get_trend_indicator(val):
                    if val > 0: return '🟢 Profit'
                    elif val < 0: return '🔴 Loss'
                    return '⚪ Flat'
                
                merged_df['Trend'] = merged_df['Hypo. P&L'].apply(get_trend_indicator)
                merged_df['Chart'] = "https://www.screener.in/company/" + merged_df['Instrument'].str.replace('.NS', '', regex=False).str.replace('.BO', '', regex=False) + "/"
                merged_df['🗑️ Delete'] = False

                # Column Ordering
                cols = [
                    'Instrument', 'Qty', 'Price Added', 'Live Price', 'Invested', 
                    'Cur. Val', 'Hypo. P&L', 'Hypo. Net Chg (%)', 'Trend', 
                    'Current Stage', 'Day Chg', '50W SMA', '% Dist from SMA', 
                    'Date Added', 'Chart', '🗑️ Delete'
                ]
                final_df = merged_df[[c for c in cols if c in merged_df.columns]]
                
                # Editor Rendering
                edited_df = st.data_editor(
                    final_df, 
                    key=f"editor_{current_list}",
                    use_container_width=True, 
                    hide_index=True, 
                    disabled=[c for c in final_df.columns if c != '🗑️ Delete'],
                    column_config={
                        "Chart": st.column_config.LinkColumn("Chart", display_text="📈 View"),
                        "🗑️ Delete": st.column_config.CheckboxColumn("🗑️ Delete", default=False)
                    }
                )
                
                # Deletion Handler
                if edited_df['🗑️ Delete'].any():
                    st.warning(f"Confirm deletion for selected items in {current_list}?")
                    if st.button(f"🗑️ Confirm Deletion", key=f"del_{current_list}", type="primary"):
                        to_keep_tickers = edited_df[edited_df['🗑️ Delete'] == False]['Instrument'].tolist()
                        # Keep rows that AREN'T in this list OR are in this list but weren't marked for deletion
                        mask = ~((watchlist_df['List Name'] == current_list) & (~watchlist_df['Instrument'].isin(to_keep_tickers)))
                        new_master = watchlist_df[mask]
                        update_sheet_full(spreadsheet_id, "Watchlists!A1", new_master)
                        st.cache_data.clear()
                        st.rerun()
            else:
                st.warning("Could not fetch live data for this list.")

# ==========================================
# MAIN PAGE UI
# ==========================================

# Initial Data Load
watchlist_df = get_sheet_data(ss_id, "Watchlists!A:D")

# Header Section
col_hdr, col_btn = st.columns([0.8, 0.2], vertical_alignment="bottom")
with col_hdr:
    st.markdown("### 👀 Watchlists")
    st.caption("Your private paper trading dashboard. Database: StockScreener_DB")

with col_btn:
    if st.button("➕ Add Stocks", type="primary", use_container_width=True):
        st.session_state.show_add_panel = not st.session_state.show_add_panel
        st.rerun()

# Inline Add Panel
if st.session_state.show_add_panel:
    with st.container(border=True):
        st.markdown("#### ⚙️ Add New Entry")
        c1, c2, c3 = st.columns(3)
        
        exist_lists = [n for n in watchlist_df['List Name'].unique() if n]
        cat_selection = c1.selectbox("Category", ["➕ New List..."] + exist_lists)
        final_cat = c1.text_input("New Category Name") if cat_selection == "➕ New List..." else cat_selection
        
        ticker_search = st_searchbox(search_yahoo_finance, key="ticker_src", label="Search Ticker")
        entry_date = c3.date_input("Hypothetical Entry Date")
        
        act1, act2 = st.columns([0.8, 0.2])
        if act1.button("➕ Auto-Fetch & Save", type="primary", use_container_width=True):
            if final_cat and ticker_search:
                with st.spinner(f"Fetching price for {ticker_search}..."):
                    try:
                        import yfinance as yf
                        stock = yf.Ticker(ticker_search)
                        end_date = entry_date + datetime.timedelta(days=7)
                        hist = stock.history(start=entry_date.strftime("%Y-%m-%d"), end=end_date.strftime("%Y-%m-%d"))
                        
                        if not hist.empty:
                            price = float(hist['Close'].iloc[0])
                            traded_date = hist.index[0].strftime("%Y-%m-%d")
                            display_ticker = ticker_search.replace('.NS', '').replace('.BO', '').upper()
                            
                            # APPEND TO GOOGLE SHEET
                            new_row = [[final_cat, display_ticker, traded_date, price]]
                            service.spreadsheets().values().append(
                                spreadsheetId=ss_id, range="Watchlists!A1",
                                valueInputOption="RAW", body={'values': new_row}).execute()
                            
                            st.success(f"Added {display_ticker} at ₹{price:.2f}")
                            st.session_state.show_add_panel = False
                            st.cache_data.clear()
                            st.rerun()
                        else:
                            st.error("Could not find price for that date.")
                    except Exception as e:
                        st.error(f"Error: {e}")
            else:
                st.error("Please fill in Category and Ticker.")
        
        if act2.button("Cancel", use_container_width=True):
            st.session_state.show_add_panel = False
            st.rerun()

st.divider()

# Rendering
if not watchlist_df.empty:
    analyze_and_render_watchlists(watchlist_df, ss_id)
else:
    st.info("Your watchlist is currently empty. Click 'Add Stocks' to start your first list!")
