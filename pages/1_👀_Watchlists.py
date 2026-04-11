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

# Set page config
st.set_page_config(page_title="Watchlists", page_icon="👀", layout="wide")

# ==========================================
# 1. THE AUTHENTICATION HANDSHAKE
# ==========================================
try:
    # No more st.connection here!
    creds = authenticate_user()
    ss_id = get_user_spreadsheet_id(creds)
    # The 'service' object is our direct pipeline to Google Sheets
    service = build('sheets', 'v4', credentials=creds)
except Exception as e:
    st.error(f"Failed to connect to your private database: {e}")
    st.stop()

if "show_add_panel" not in st.session_state:
    st.session_state.show_add_panel = False

# ==========================================
# 2. DATA LOADERS (API VERSION)
# ==========================================
def get_sheet_data(spreadsheet_id, range_name):
    """Fetch data using the official API instead of st.connection"""
    try:
        result = service.spreadsheets().values().get(
            spreadsheetId=spreadsheet_id, 
            range=range_name
        ).execute()
        values = result.get('values', [])
        if not values or len(values) < 1:
            return pd.DataFrame(columns=["List Name", "Instrument", "Date Added", "Price Added"])
        # Use first row as header, rest as data
        return pd.DataFrame(values[1:], columns=values[0])
    except Exception as e:
        # If range doesn't exist yet, return empty DF
        return pd.DataFrame(columns=["List Name", "Instrument", "Date Added", "Price Added"])

def update_sheet_full(spreadsheet_id, range_name, df):
    """Overwrites the sheet (crucial for Deletions)"""
    # 1. Clear current data
    service.spreadsheets().values().clear(spreadsheetId=spreadsheet_id, range=range_name).execute()
    # 2. Prepare new payload (headers + data)
    body = {'values': [df.columns.tolist()] + df.values.tolist()}
    # 3. Update
    service.spreadsheets().values().update(
        spreadsheetId=spreadsheet_id, range=range_name,
        valueInputOption="RAW", body=body).execute()

# ==========================================
# 3. UI SEARCH & RENDERING
# ==========================================
def search_yahoo_finance(searchterm: str):
    if not searchterm or len(searchterm) < 2: return []
    url = f"https://query2.finance.yahoo.com/v1/finance/search?q={searchterm}&quotesCount=10"
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        resp = requests.get(url, headers=headers).json()
        return [(f"{q.get('shortname')} ({q.get('symbol')})", q.get('symbol')) 
                for q in resp.get('quotes', []) if ('.NS' in q.get('symbol') or '.BO' in q.get('symbol'))]
    except: return []

def analyze_and_render_watchlists(watchlist_df, spreadsheet_id):
    # Ensure columns are numeric for math
    watchlist_df['Price Added'] = pd.to_numeric(watchlist_df['Price Added'], errors='coerce').fillna(0)
    
    list_names = [n for n in watchlist_df['List Name'].unique() if n]
    if not list_names:
        st.info("Your watchlist is empty. Click 'Add Stocks' to start!")
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
                merged_df['Qty'] = merged_df['Price Added'].apply(lambda x: int(round(100000 / x)) if x > 0 else 0)
                merged_df['Invested'] = 100000.0
                merged_df['Cur. Val'] = merged_df['Live Price'] * merged_df['Qty']
                merged_df['Hypo. P&L'] = merged_df['Cur. Val'] - merged_df['Invested']
                merged_df['Hypo. Net Chg (%)'] = (merged_df['Hypo. P&L'] / 1000).round(2)
                
                def get_trend(val):
                    return '🟢 Profit' if val > 0 else '🔴 Loss' if val < 0 else '⚪ Flat'
                
                merged_df['Trend'] = merged_df['Hypo. P&L'].apply(get_trend)
                merged_df['Chart'] = "https://www.screener.in/company/" + merged_df['Instrument'].str.replace('.NS','').str.replace('.BO','') + "/"
                merged_df['🗑️ Delete'] = False

                cols = [
                    'Instrument', 'Qty', 'Price Added', 'Live Price', 'Invested', 
                    'Cur. Val', 'Hypo. P&L', 'Hypo. Net Chg (%)', 'Trend', 
                    'Current Stage', 'Day Chg', '50W SMA', '% Dist from SMA', 
                    'Date Added', 'Chart', '🗑️ Delete'
                ]
                final_df = merged_df[[c for c in cols if c in merged_df.columns]]
                
                edited_df = st.data_editor(
                    final_df, 
                    key=f"ed_{current_list}",
                    use_container_width=True, 
                    hide_index=True, 
                    disabled=[c for c in final_df.columns if c != '🗑️ Delete'],
                    column_config={"Chart": st.column_config.LinkColumn("Chart", display_text="📈 View")}
                )
                
                if edited_df['🗑️ Delete'].any():
                    if st.button("🗑️ Confirm Deletion", key=f"btn_{current_list}", type="primary"):
                        to_keep = edited_df[edited_df['🗑️ Delete'] == False]['Instrument'].tolist()
                        mask = ~((watchlist_df['List Name'] == current_list) & (~watchlist_df['Instrument'].isin(to_keep)))
                        new_df = watchlist_df[mask]
                        update_sheet_full(spreadsheet_id, "Watchlists!A1", new_df)
                        st.cache_data.clear()
                        st.rerun()
            else:
                st.warning("Could not fetch live market data.")

# ==========================================
# 4. MAIN UI EXECUTION
# ==========================================
watchlist_df = get_sheet_data(ss_id, "Watchlists!A:D")

col_hdr, col_btn = st.columns([0.8, 0.2], vertical_alignment="bottom")
col_hdr.markdown("### 👀 Private Watchlists")
col_hdr.caption(f"Authenticated as: {st.session_state.credentials.to_json()[:10]}... | DB: StockScreener_DB")

if col_btn.button("➕ Add Stocks", type="primary", use_container_width=True):
    st.session_state.show_add_panel = not st.session_state.show_add_panel
    st.rerun()

if st.session_state.show_add_panel:
    with st.container(border=True):
        st.markdown("#### ⚙️ Add New Stock Entry")
        c1, c2, c3 = st.columns(3)
        exist_lists = [n for n in watchlist_df['List Name'].unique() if n]
        cat = c1.selectbox("Category", ["➕ New List..."] + exist_lists)
        final_cat = c1.text_input("Name") if cat == "➕ New List..." else cat
        ticker = st_searchbox(search_yahoo_finance, key="t_src", label="Search Ticker")
        date = c3.date_input("Date")
        
        a1, a2 = st.columns([0.8, 0.2])
        if a1.button("➕ Save to My Drive", type="primary", use_container_width=True):
            if final_cat and ticker:
                with st.spinner("Fetching historical price..."):
                    try:
                        import yfinance as yf
                        tk = yf.Ticker(ticker)
                        h = tk.history(start=date.strftime("%Y-%m-%d"), end=(date + datetime.timedelta(days=7)).strftime("%Y-%m-%d"))
                        if not h.empty:
                            row = [[final_cat, ticker.replace('.NS','').replace('.BO','').upper(), h.index[0].strftime("%Y-%m-%d"), float(h['Close'].iloc[0])]]
                            service.spreadsheets().values().append(
                                spreadsheetId=ss_id, range="Watchlists!A1",
                                valueInputOption="RAW", body={'values': row}).execute()
                            st.success("Saved successfully!")
                            st.session_state.show_add_panel = False
                            st.cache_data.clear()
                            st.rerun()
                    except Exception as e: st.error(f"Error: {e}")
        if a2.button("Cancel", use_container_width=True):
            st.session_state.show_add_panel = False
            st.rerun()

st.divider()
analyze_and_render_watchlists(watchlist_df, ss_id)
