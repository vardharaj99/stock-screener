import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import warnings
import requests
from streamlit_searchbox import st_searchbox
from modules.market_math import fetch_live_data_and_stage
import datetime
import yfinance as yf

warnings.filterwarnings('ignore')

st.set_page_config(page_title="Paper Trading", page_icon="👀", layout="wide")

SPREADSHEET = "https://docs.google.com/spreadsheets/d/18ci-lXIJAhb-T96DZ1bL5sEKVmishPTBItIMaACBRJw/edit?gid=0#gid=0"

if "show_add_panel" not in st.session_state:
    st.session_state.show_add_panel = False

def search_yahoo_finance(searchterm: str):
    if not searchterm or len(searchterm) < 2:
        return []
    url = f"https://query2.finance.yahoo.com/v1/finance/search?q={searchterm}&quotesCount=10"
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        response = requests.get(url, headers=headers)
        quotes = response.json().get('quotes', [])
        return [(f"{q.get('shortname')} ({q.get('symbol')})", q.get('symbol')) for q in quotes if ('.NS' in q.get('symbol') or '.BO' in q.get('symbol'))]
    except:
        return []

def analyze_and_render_watchlists(watchlist_df, conn):
    list_names = [n for n in watchlist_df['List Name'].unique() if pd.notnull(n) and str(n).strip() != '']
    if not list_names:
        return

    raw_tickers = [str(t).strip() for t in watchlist_df['Instrument'].tolist() if pd.notnull(t)]
    tickers = [t + ".NS" if not ('.NS' in t or '.BO' in t) else t for t in raw_tickers]
    
    with st.spinner("Updating prices and fixing missing data..."):
        results, _ = fetch_live_data_and_stage(tickers)
    
    if not results:
        st.warning("Market data unavailable.")
        return

    live_df = pd.DataFrame(results)
    
    def to_f(v):
        try:
            if pd.isna(v) or str(v).strip() == "": return 0.0
            return float(str(v).replace(',', '').strip())
        except: return 0.0

    master_df = pd.merge(watchlist_df, live_df, left_on='Instrument', right_on='Ticker', how='left')
    master_df['Price Added'] = master_df['Price Added'].apply(to_f)

    # --- VERSATILITY LOGIC: FIX MISSING PRICES ---
    if (master_df['Price Added'] == 0).any():
        for idx, row in master_df[master_df['Price Added'] == 0].iterrows():
            try:
                t_sym = row['Instrument']
                if not ('.NS' in t_sym or '.BO' in t_sym): t_sym += '.NS'
                
                # 1. Try historical fetch if date exists
                if pd.notnull(row['Date Added']) and str(row['Date Added']).strip() != "":
                    d_obj = pd.to_datetime(row['Date Added'])
                    h_data = yf.Ticker(t_sym).history(start=d_obj, end=d_obj + datetime.timedelta(days=7))
                    if not h_data.empty:
                        master_df.at[idx, 'Price Added'] = h_data['Close'].iloc[0]
                        continue
                
                # 2. Fallback to Live Price
                master_df.at[idx, 'Price Added'] = row['Live Price']
            except:
                pass

    # Calculations
    master_df['Qty'] = master_df['Price Added'].apply(lambda x: int(round(100000 / x)) if x > 0 else 0)
    master_df['Invested'] = master_df['Qty'] * master_df['Price Added']
    master_df['Cur. Val'] = master_df['Live Price'] * master_df['Qty']
    master_df['P&L'] = master_df['Cur. Val'] - master_df['Invested']

    # --- GLOBAL AGGREGATES ---
    t_inv, t_val = master_df['Invested'].sum(), master_df['Cur. Val'].sum()
    t_pnl = t_val - t_inv
    t_pct = (t_pnl / t_inv * 100) if t_inv > 0 else 0

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Watchlist Value", f"₹{t_val:,.2f}")
    m2.metric("Total Invested", f"₹{t_inv:,.2f}")
    m3.metric("Total P&L", f"₹{t_pnl:,.2f}", delta=f"{t_pct:.2f}%")
    m4.metric("Stocks", len(master_df))
    st.divider()

    tabs = st.tabs(list_names)
    for tab, current_list in zip(tabs, list_names):
        with tab:
            df = master_df[master_df['List Name'] == current_list].copy()
            l_inv, l_val = df['Invested'].sum(), df['Cur. Val'].sum()
            l_pnl, l_pct = (l_val - l_inv), ((l_val - l_inv) / l_inv * 100 if l_inv > 0 else 0)
            
            c1, c2, c3 = st.columns(3)
            c1.caption(f"Invested: ₹{l_inv:,.0f}")
            c2.caption(f"Current: ₹{l_val:,.0f}")
            c3.markdown(f"P&L: :{'green' if l_pnl >= 0 else 'red'}[₹{l_pnl:,.2f} ({l_pct:.2f}%)]")

            df['Net Chg %'] = (df['P&L'] / df['Invested'] * 100).fillna(0)
            df['Trend'] = df['P&L'].apply(lambda x: '🟢 Profit' if x > 0 else '🔴 Loss' if x < 0 else '⚪ Flat')
            df['Chart'] = "https://www.screener.in/company/" + df['Instrument'] + "/"
            df['🗑️ Delete'] = False

            cols = ['Instrument', 'Qty', 'Price Added', 'Live Price', 'Invested', 'Cur. Val', 'P&L', 'Net Chg %', 'Trend', 'Current Stage', 'Day Chg', '50W SMA', '% Dist from SMA', 'Date Added', 'Chart', '🗑️ Delete']
            disp = df[[c for c in cols if c in df.columns]]
            num = disp.select_dtypes(include=['float64', 'int64']).columns
            disp[num] = disp[num].round(2)

            edited_df = st.data_editor(
                disp, key=f"e_{current_list}", use_container_width=True, hide_index=True,
                disabled=[c for c in disp.columns if c != '🗑️ Delete'],
                column_config={"Chart": st.column_config.LinkColumn("Chart", display_text="📈 View")}
            )
            
            to_del = edited_df[edited_df['🗑️ Delete'] == True]['Instrument'].tolist()
            if to_del:
                if st.button("🗑️ Confirm Delete", key=f"b_{current_list}", type="primary"):
                    mask = ~((watchlist_df['List Name'] == current_list) & (watchlist_df['Instrument'].isin(to_del)))
                    conn.update(spreadsheet=SPREADSHEET, worksheet="Watchlists", data=watchlist_df[mask])
                    st.cache_data.clear()
                    st.rerun()

try:
    conn = st.connection("gsheets", type=GSheetsConnection)
    raw = conn.read(spreadsheet=SPREADSHEET, worksheet="Watchlists", ttl="5m")
    wdf = pd.DataFrame(raw) if not raw.empty else pd.DataFrame(columns=['List Name', 'Instrument', 'Date Added', 'Price Added'])

    h_l, h_r = st.columns([0.8, 0.2], vertical_alignment="bottom")
    h_l.markdown("### 👀 Watchlists")
    if h_r.button("➕ Add Stocks", type="primary", use_container_width=True):
        st.session_state.show_add_panel = not st.session_state.show_add_panel
        st.rerun()

    if st.session_state.show_add_panel:
        with st.container(border=True):
            st.markdown("#### ⚙️ Add Entry")
            l_opts = ["➕ New..."] + sorted([str(x) for x in wdf['List Name'].unique() if pd.notnull(x)])
            c1, c2, c3 = st.columns(3)
            sl = c1.selectbox("Category", l_opts)
            fl = c1.text_input("Name") if sl == "➕ New..." else sl
            nt = st_searchbox(search_yahoo_finance, key="t_src", label="Ticker")
            nd = c3.date_input("Date")
            
            if st.button("➕ Save", type="primary"):
                if fl and nt:
                    ts = nt.upper() if ('.NS' in nt.upper() or '.BO' in nt.upper()) else nt.upper() + '.NS'
                    h = yf.Ticker(ts).history(start=nd, end=nd + datetime.timedelta(days=7))
                    if not h.empty:
                        p = float(h['Close'].iloc[0])
                        doc = conn.client._client.open_by_url(SPREADSHEET)
                        ws = doc.worksheet("Watchlists")
                        ws.append_row([fl, nt.replace('.NS','').replace('.BO','').upper(), h.index[0].strftime("%Y-%m-%d"), p])
                        st.session_state.show_add_panel = False
                        st.cache_data.clear()
                        st.rerun()
            if st.button("Cancel"):
                st.session_state.show_add_panel = False
                st.rerun()

    if not wdf.empty:
        analyze_and_render_watchlists(wdf, conn)
    else:
        st.info("Watchlist is empty.")

except Exception as e:
    st.error(f"Error: {e}")
