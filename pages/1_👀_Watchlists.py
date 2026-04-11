import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import warnings
import requests
from streamlit_searchbox import st_searchbox
from modules.market_math import fetch_live_data_and_stage

warnings.filterwarnings('ignore')

st.set_page_config(page_title="Paper Trading", page_icon="👀", layout="wide")

SPREADSHEET = "https://docs.google.com/spreadsheets/d/18ci-lXIJAhb-T96DZ1bL5sEKVmishPTBItIMaACBRJw/edit?gid=0#gid=0"

# Initialize state for the slide-down panel
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
# RENDER LOGIC
# ==========================================
def analyze_and_render_watchlists(watchlist_df):
    required_cols = ['List Name', 'Instrument', 'Date Added', 'Price Added']
    if not all(col in watchlist_df.columns for col in required_cols):
        st.error(f"Watchlist sheet is missing columns. It must exactly have: {', '.join(required_cols)}")
        return

    list_names = [name for name in watchlist_df['List Name'].unique() if pd.notnull(name) and str(name).strip() != '']
    if len(list_names) == 0:
        return

    tabs = st.tabs(list_names)
    for tab, current_list in zip(tabs, list_names):
        with tab:
            df = watchlist_df[watchlist_df['List Name'] == current_list].copy()
            
            raw_tickers = [str(t).strip() for t in df['Instrument'].tolist() if pd.notnull(t)]
            tickers = [t + ".NS" if not t.endswith(".NS") else t for t in raw_tickers]
            
            with st.spinner(f"Fetching live data for {current_list} watchlist..."):
                results, errors = fetch_live_data_and_stage(tickers)
            
            if results:
                analysis_df = pd.DataFrame(results)
                merged_df = pd.merge(df, analysis_df, left_on='Instrument', right_on='Ticker', how='left')
                if 'Ticker' in merged_df.columns: merged_df = merged_df.drop(columns=['Ticker'])
                
                def clean_price(val):
                    try:
                        return float(str(val).replace(',', '').strip())
                    except:
                        return 0.0
                
                merged_df['Price Added'] = merged_df['Price Added'].apply(clean_price)
                
                merged_df['Qty'] = merged_df['Price Added'].apply(lambda x: int(round(100000 / x)) if x > 0 else 0)
                merged_df['Invested'] = 100000.0
                merged_df['Cur. Val'] = merged_df['Live Price'] * merged_df['Qty']
                merged_df['Hypo. P&L'] = merged_df['Cur. Val'] - merged_df['Invested']
                merged_df['Hypo. Net Chg (%)'] = (merged_df['Hypo. P&L'] / merged_df['Invested']) * 100
                
                def get_trend_indicator(val):
                    try:
                        v = float(val)
                        if v > 0: return '🟢 Profit'
                        elif v < 0: return '🔴 Loss'
                    except:
                        pass
                    return '⚪ Flat'
                
                merged_df['Trend'] = merged_df['Hypo. P&L'].apply(get_trend_indicator)
                merged_df['Chart'] = "https://www.screener.in/company/" + merged_df['Instrument'] + "/"

                cols = [
                    'Instrument', 'Chart', 'Date Added', 'Price Added', 'Qty', 'Invested', 
                    'Live Price', 'Cur. Val', 'Trend', 'Hypo. P&L', 'Hypo. Net Chg (%)', 
                    'Current Stage', 'Day Chg', '50W SMA', '% Dist from SMA'
                ]
                merged_df = merged_df[[c for c in cols if c in merged_df.columns]]
                
                numeric_cols = merged_df.select_dtypes(include=['float64', 'int64']).columns
                merged_df[numeric_cols] = merged_df[numeric_cols].round(2)
                
                st.dataframe(
                    merged_df, 
                    use_container_width=True, 
                    hide_index=True,
                    column_config={
                        "Chart": st.column_config.LinkColumn("Chart", help="Click to open Screener.in", display_text="📈 View")
                    }
                )
            else:
                st.warning("Could not fetch data for this list.")

try:
    conn = st.connection("gsheets", type=GSheetsConnection)
    doc = conn.client._client.open_by_url(SPREADSHEET)
    
    try:
        ws_watchlists = doc.worksheet("Watchlists")
    except Exception:
        ws_watchlists = doc.add_worksheet(title="Watchlists", rows="100", cols="20")
        ws_watchlists.append_row(["List Name", "Instrument", "Date Added", "Price Added"])
    
    raw_watchlist_df = conn.read(spreadsheet=SPREADSHEET, worksheet="Watchlists", ttl="5m")
    
    if not raw_watchlist_df.empty:
        watchlist_df = pd.DataFrame(raw_watchlist_df.values.tolist(), columns=raw_watchlist_df.columns)
    else:
        watchlist_df = raw_watchlist_df

    existing_lists = []
    if 'List Name' in watchlist_df.columns:
        existing_lists = [str(name).strip() for name in watchlist_df['List Name'].unique() if pd.notnull(name) and str(name).strip() != '']

    # ==========================================
    # HEADER & TOGGLE BUTTON
    # ==========================================
    col_hdr, col_btn = st.columns([0.85, 0.15], vertical_alignment="bottom")
    
    with col_hdr:
        st.markdown("### 👀 Watchlists")
        st.caption("Track hypothetical entry points. Invested amount is standardized at ₹1,00,000 per stock.")
        
    with col_btn:
        # Toggles the state securely so it survives page re-runs
        if st.button("➕ Add Stocks", type="primary", use_container_width=True):
            st.session_state.show_add_panel = not st.session_state.show_add_panel
            st.rerun()
            
    # ==========================================
    # INLINE CONTROL PANEL (Immune to Searchbox Crashes!)
    # ==========================================
    if st.session_state.show_add_panel:
        with st.container(border=True):
            st.markdown("#### ⚙️ Add New Stock")
            
            list_options = ["➕ Create New List..."] + existing_lists
            
            col1, col2, col3 = st.columns(3)
            
            selected_list = col1.selectbox("Watchlist Category", options=list_options)
            if selected_list == "➕ Create New List...":
                final_list_name = col1.text_input("Enter New List Name", placeholder="e.g. Pharma, Defence")
            else:
                final_list_name = selected_list
                
            with col2:
                new_ticker = st_searchbox(
                    search_yahoo_finance,
                    key="ticker_search_panel",
                    label="Search Ticker", 
                    placeholder="Type to search (e.g. TATA)...",
                    clear_on_submit=False
                )
                    
            new_date = col3.date_input("Hypothetical Entry Date")
            
            # Action Buttons Layout
            action_col1, action_col2 = st.columns([0.8, 0.2])
            
            with action_col1:
                if st.button("➕ Auto-Fetch Price & Save", type="primary"):
                    if final_list_name and new_ticker:
                        ticker_symbol = new_ticker.strip().upper()
                        if not ticker_symbol.endswith('.NS') and not ticker_symbol.endswith('.BO'):
                            ticker_symbol += '.NS' 
                        
                        with st.spinner(f"Fetching historical price for {ticker_symbol}..."):
                            try:
                                import yfinance as yf
                                stock = yf.Ticker(ticker_symbol)
                                end_date = new_date + pd.Timedelta(days=7)
                                hist = stock.history(start=new_date.strftime("%Y-%m-%d"), end=end_date.strftime("%Y-%m-%d"))
                                
                                if not hist.empty:
                                    fetched_price = float(hist['Close'].iloc[0])
                                    actual_traded_date = hist.index[0].strftime("%Y-%m-%d")
                                    display_ticker = new_ticker.replace('.NS', '').replace('.BO', '').upper()
                                    
                                    ws_watchlists.append_row([
                                        final_list_name.strip(), 
                                        display_ticker, 
                                        actual_traded_date, 
                                        fetched_price
                                    ])
                                    st.success(f"Successfully added {display_ticker}! Entry logged at ₹{fetched_price:.2f}.")
                                    # Auto-close the panel on success
                                    st.session_state.show_add_panel = False 
                                    st.cache_data.clear()
                                    st.rerun()
                                else:
                                    st.error("Could not find trading data near that date.")
                            except Exception as e:
                                st.error(f"Error fetching price: {e}")
                    else:
                        st.error("Please provide both a List Name and select a Stock Ticker.")
                        
            with action_col2:
                if st.button("Cancel", use_container_width=True):
                    st.session_state.show_add_panel = False
                    st.rerun()

    st.divider()

    # ==========================================
    # RENDER THE MAIN DASHBOARD
    # ==========================================
    if not watchlist_df.empty and len(watchlist_df) > 0:
        analyze_and_render_watchlists(watchlist_df)
    else:
        st.info("Your watchlist is empty. Click 'Add Stocks' to begin!")
        
except Exception as e:
    st.error(f"A critical error occurred while connecting to Google Sheets: {e}")
