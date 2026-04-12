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
    headers = {'User-Agent': 'Mozilla/5.0'}
    
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
        return results
    except Exception:
        return []

# ==========================================
# RENDER LOGIC WITH AGGREGATES
# ==========================================
def analyze_and_render_watchlists(watchlist_df, conn):
    list_names = [name for name in watchlist_df['List Name'].unique() if pd.notnull(name) and str(name).strip() != '']
    if not list_names:
        return

    # Fetch live data for the entire sheet for Global Aggregates
    raw_tickers = [str(t).strip() for t in watchlist_df['Instrument'].tolist() if pd.notnull(t)]
    tickers = [t + ".NS" if not (t.endswith(".NS") or t.endswith(".BO")) else t for t in raw_tickers]
    
    with st.spinner("Updating market prices..."):
        results, _ = fetch_live_data_and_stage(tickers)
    
    if not results:
        st.warning("Live market data unavailable.")
        return

    # Data Processing
    live_df = pd.DataFrame(results)
    
    def clean_val(val):
        try: return float(str(val).replace(',', '').strip())
        except: return 0.0

    master_df = pd.merge(watchlist_df, live_df, left_on='Instrument', right_on='Ticker', how='left')
    master_df['Price Added'] = master_df['Price Added'].apply(clean_val)
    master_df['Qty'] = master_df['Price Added'].apply(lambda x: int(round(100000 / x)) if x > 0 else 0)
    master_df['Invested'] = master_df['Qty'] * master_df['Price Added']
    master_df['Cur. Val'] = master_df['Live Price'] * master_df['Qty']
    master_df['P&L'] = master_df['Cur. Val'] - master_df['Invested']

    # ==========================================
    # GLOBAL SUMMARY (The requested Header Level)
    # ==========================================
    t_inv = master_df['Invested'].sum()
    t_val = master_df['Cur. Val'].sum()
    t_pnl = t_val - t_inv
    t_pnl_pct = (t_pnl / t_inv * 100) if t_inv > 0 else 0

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Watchlist Value", f"₹{t_val:,.2f}")
    m2.metric("Total Invested", f"₹{t_inv:,.2f}")
    m3.metric("Total P&L", f"₹{t_pnl:,.2f}", delta=f"{t_pnl_pct:.2f}%")
    m4.metric("Stocks Tracked", len(master_df))
    st.divider()

    # ==========================================
    # CATEGORY TABS
    # ==========================================
    tabs = st.tabs(list_names)
    for tab, current_list in zip(tabs, list_names):
        with tab:
            df = master_df[master_df['List Name'] == current_list].copy()
            
            # Category Aggregate Info
            l_inv = df['Invested'].sum()
            l_val = df['Cur. Val'].sum()
            l_pnl = l_val - l_inv
            l_pnl_pct = (l_pnl / l_inv * 100) if l_inv > 0 else 0
            
            c1, c2, c3 = st.columns(3)
            c1.caption(f"**Invested:** ₹{l_inv:,.0f}")
            c2.caption(f"**Current:** ₹{l_val:,.0f}")
            c3.markdown(f"**P&L:** :{'green' if l_pnl >= 0 else 'red'}[₹{l_pnl:,.2f} ({l_pnl_pct:.2f}%)]")

            # Final Column Cleanup
            df['Hypo. Net Chg (%)'] = (df['P&L'] / df['Invested'] * 100).fillna(0)
            df['Trend'] = df['P&L'].apply(lambda x: '🟢 Profit' if x > 0 else '🔴 Loss' if x < 0 else '⚪ Flat')
            df['Chart'] = "https://www.screener.in/company/" + df['Instrument'] + "/"
            df['🗑️ Delete'] = False

            cols = [
                'Instrument', 'Qty', 'Price Added', 'Live Price', 'Invested', 
                'Cur. Val', 'P&L', 'Hypo. Net Chg (%)', 'Trend', 
                'Current Stage', 'Day Chg', '50W SMA', '% Dist from SMA', 
                'Date Added', 'Chart', '🗑️ Delete'
            ]
            
            display_df = df[[c for c in cols if c in df.columns]]
            
            # Rounding
            num_cols = display_df.select_dtypes(include=['float64', 'int64']).columns
            display_df[num_cols] = display_df[num_cols].round(2)

            edited_df = st.data_editor(
                display_df, 
                key=f"ed_{current_list}",
                use_container_width=True, 
                hide_index=True,
                disabled=[c for c in display_df.columns if c != '🗑️ Delete'],
                column_config={
                    "Chart": st.column_config.LinkColumn("Chart", display_text="📈 View"),
                    "P&L": st.column_config.NumberColumn("P&L", format="₹%.2f"),
                    "Invested": st.column_config.NumberColumn("Invested", format="₹%.0f")
                }
            )
            
            # Deletion Logic
            to_del = edited_df[edited_df['🗑️ Delete'] == True]['Instrument'].tolist()
            if to_del:
                if st.button("🗑️ Confirm Deletion", key=f"btn_{current_list}", type="primary"):
                    mask = ~((watchlist_df['List Name'] == current_list) & (watchlist_df['Instrument'].isin(to_del)))
                    conn.update(spreadsheet=SPREADSHEET, worksheet="Watchlists", data=watchlist_df[mask])
                    st.cache_data.clear()
                    st.rerun()

# ==========================================
# MAIN PAGE START
# ==========================================
try:
    conn = st.connection("gsheets", type=GSheetsConnection)
    raw_df = conn.read(spreadsheet=SPREADSHEET, worksheet="Watchlists", ttl="5m")
    watchlist_df = pd.DataFrame(raw_df) if not raw_df.empty else pd.DataFrame(columns=['List Name', 'Instrument', 'Date Added', 'Price Added'])

    # Header and Add Logic
    c_h, c_b = st.columns([0.8, 0.2], vertical_alignment="bottom")
    c_h.markdown("### 👀 Private Watchlists")
    
    if c_b.button("➕ Add Stocks", type="primary", use_container_width=True):
        st.session_state.show_add_panel = not st.session_state.show_add_panel
        st.rerun()

    if st.session_state.show_add_panel:
        with st.container(border=True):
            st.markdown("#### ⚙️ Add New Entry")
            l_opt = ["➕ New List..."] + sorted([str(x) for x in watchlist_df['List Name'].unique() if pd.notnull(x)])
            
            col1, col2, col3 = st.columns(3)
            sel_l = col1.selectbox("Category", options=l_opt)
            final_l = col1.text_input("List Name") if sel_l == "➕ New List..." else sel_l
            new_t = st_searchbox(search_yahoo_finance, key="t_src", label="Ticker")
            new_d = col3.date_input("Entry Date")
            
            a1, a2 = st.columns([0.8, 0.2])
            if a1.button("➕ Save Entry", type="primary", use_container_width=True):
                if final_l and new_t:
                    import yfinance as yf
                    t_sym = new_t.upper()
                    if not (t_sym.endswith('.NS') or t_sym.endswith('.BO')): t_sym += '.NS'
                    
                    hist = yf.Ticker(t_sym).history(start=new_d, end=new_d + datetime.timedelta(days=7))
                    if not hist.empty:
                        price = float(hist['Close
