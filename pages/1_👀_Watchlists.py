import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import warnings
import json  # <-- We need this to nuke the PyArrow backend
from modules.market_math import fetch_live_data_and_stage

warnings.filterwarnings('ignore')

st.set_page_config(page_title="Paper Trading", page_icon="👀", layout="wide")
st.title("👀 Paper Trading Watchlists")
st.markdown("Track hypothetical entry points based on Stage Analysis.")

SPREADSHEET = "https://docs.google.com/spreadsheets/d/18ci-lXIJAhb-T96DZ1bL5sEKVmishPTBItIMaACBRJw/edit?gid=0#gid=0"

def analyze_and_render_watchlists(watchlist_df):
    required_cols = ['List Name', 'Instrument', 'Date Added', 'Price Added']
    if not all(col in watchlist_df.columns for col in required_cols):
        st.error(f"Watchlist sheet is missing columns. It must exactly have: {', '.join(required_cols)}")
        return

    list_names = watchlist_df['List Name'].dropna().unique()
    if len(list_names) == 0:
        return

    tabs = st.tabs(list_names)
    for tab, current_list in zip(tabs, list_names):
        with tab:
            df = watchlist_df[watchlist_df['List Name'] == current_list].copy()
            raw_tickers = df['Instrument'].astype(str).str.strip().tolist()
            tickers = [t + ".NS" if not t.endswith(".NS") else t for t in raw_tickers]
            
            with st.spinner(f"Fetching live data for {current_list} watchlist..."):
                results, errors = fetch_live_data_and_stage(tickers)
            
            if results:
                analysis_df = pd.DataFrame(results)
                merged_df = pd.merge(df, analysis_df, left_on='Instrument', right_on='Ticker', how='left')
                if 'Ticker' in merged_df.columns: merged_df = merged_df.drop(columns=['Ticker'])
                
                merged_df['Price Added'] = pd.to_numeric(merged_df['Price Added'].astype(str).str.replace(',', ''), errors='coerce')
                
                merged_df['Hypo. P&L'] = merged_df['Live Price'] - merged_df['Price Added']
                merged_df['Hypo. Net Chg (%)'] = (merged_df['Hypo. P&L'] / merged_df['Price Added']) * 100
                
                cols = ['Instrument', 'List Name', 'Date Added', 'Price Added', 'Live Price', 'Day Chg', 'Hypo. P&L', 'Hypo. Net Chg (%)', 'Current Stage', '50W SMA', '% Dist from SMA']
                merged_df = merged_df[[c for c in cols if c in merged_df.columns]]
                
                numeric_cols = merged_df.select_dtypes(include=['float64', 'int64']).columns
                merged_df[numeric_cols] = merged_df[numeric_cols].round(2)
                
                # ==========================================
                # THE BULLETPROOF PYARROW FIX
                # ==========================================
                # Serialize to JSON and back to completely sever any PyArrow memory links
                raw_json = merged_df.to_json(orient="records")
                clean_df = pd.DataFrame(json.loads(raw_json))
                
                # Safe coloring function that won't crash on empty cells
                def apply_color(x):
                    try:
                        val = float(x)
                        if val > 0: return 'color: green'
                        elif val < 0: return 'color: red'
                    except:
                        pass
                    return ''

                style_cols = [c for c in ['Hypo. P&L', 'Hypo. Net Chg (%)', 'Day Chg'] if c in clean_df.columns]
                
                # Check pandas version and apply the styler securely
                styler = clean_df.style
                if hasattr(styler, "map"):
                    styled_df = styler.map(apply_color, subset=style_cols)
                else:
                    styled_df = styler.applymap(apply_color, subset=style_cols)
                
                st.dataframe(styled_df, use_container_width=True, hide_index=True)
                # ==========================================
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
    
    watchlist_df = conn.read(spreadsheet=SPREADSHEET, worksheet="Watchlists", ttl="5m")

    with st.expander("⚙️ Add New Stock to Watchlist", expanded=True):
        with st.form("add_stock_form", clear_on_submit=True):
            st.caption("Add stocks here and they will be saved to your Google Sheet automatically.")
            col1, col2, col3, col4 = st.columns(4)
            
            new_list = col1.text_input("List Name", placeholder="e.g. Pharma, Defence")
            new_ticker = col2.text_input("Stock Ticker", placeholder="e.g. SUNPHARMA, HAL")
            new_date = col3.date_input("Date Added")
            new_price = col4.number_input("Entry Price (₹)", min_value=0.0, format="%.2f")
            
            submitted = st.form_submit_button("➕ Save to Watchlist")
            if submitted:
                if new_list and new_ticker and new_price > 0:
                    ws_watchlists.append_row([
                        new_list.strip(), 
                        new_ticker.strip().upper(), 
                        new_date.strftime("%Y-%m-%d"), 
                        float(new_price)
                    ])
                    st.success(f"Successfully added {new_ticker.upper()} to the {new_list} list!")
                    st.cache_data.clear()
                    st.rerun()
                else:
                    st.error("Please fill out all fields and ensure the price is greater than 0.")
                    
    if not watchlist_df.empty and len(watchlist_df) > 0:
        analyze_and_render_watchlists(watchlist_df)
    else:
        st.info("Your watchlist is empty. Use the form above to add your first stock!")
        
except Exception as e:
    st.error(f"A critical error occurred while connecting to Google Sheets: {e}")
