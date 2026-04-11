import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import warnings
from modules.market_math import fetch_live_data_and_stage

warnings.filterwarnings('ignore')

st.set_page_config(page_title="My Portfolios", page_icon="💼", layout="wide")
st.title("💼 Stage Analysis Portfolios")
st.markdown("Fetching securely authenticated portfolio data and **live market prices**...")

SPREADSHEET = "https://docs.google.com/spreadsheets/d/18ci-lXIJAhb-T96DZ1bL5sEKVmishPTBItIMaACBRJw/edit?gid=0#gid=0"

def analyze_and_render_profile(holdings_df, profile_name):
    if 'Instrument' not in holdings_df.columns:
        st.info(f"Sheet '{profile_name}' is empty or missing the 'Instrument' column.")
        return

    raw_tickers = holdings_df['Instrument'].dropna().astype(str).str.strip().tolist()
    tickers = [t + ".NS" if not t.endswith(".NS") else t for t in raw_tickers]
    
    with st.spinner(f"Analyzing {len(tickers)} stocks for {profile_name}..."):
        results, errors = fetch_live_data_and_stage(tickers)

    if results:
        analysis_df = pd.DataFrame(results)
        merged_df = pd.merge(holdings_df, analysis_df, left_on='Instrument', right_on='Ticker', how='left')
        
        if 'Ticker' in merged_df.columns: merged_df = merged_df.drop(columns=['Ticker'])
        static_cols = ['LTP', 'Day chg.', 'Day Chg.', 'Cur. val', 'Cur. Val', 'P&L', 'Net chg.', 'Net Chg.']
        merged_df = merged_df.drop(columns=[col for col in static_cols if col in merged_df.columns])
        
        if 'Qty.' in merged_df.columns and 'Qty' not in merged_df.columns: merged_df = merged_df.rename(columns={'Qty.': 'Qty'})
        if 'Qty' in merged_df.columns: merged_df['Qty'] = pd.to_numeric(merged_df['Qty'].astype(str).str.replace(',', ''), errors='coerce')
        if 'Invested' in merged_df.columns: merged_df['Invested'] = pd.to_numeric(merged_df['Invested'].astype(str).str.replace(',', ''), errors='coerce')

        if 'Qty' in merged_df.columns and 'Invested' in merged_df.columns:
            merged_df['Cur. Val'] = merged_df['Live Price'] * merged_df['Qty']
            merged_df['P&L'] = merged_df['Cur. Val'] - merged_df['Invested']
            merged_df['Net Chg'] = ((merged_df['Cur. Val'] - merged_df['Invested']) / merged_df['Invested']) * 100

            total_invested = merged_df['Invested'].sum()
            total_current = merged_df['Cur. Val'].sum()
            total_pl = total_current - total_invested
            total_pl_pct = (total_pl / total_invested) * 100 if total_invested > 0 else 0
            
            col1, col2, col3, col4 = st.columns(4)
            col1.metric("Total Invested", f"₹{total_invested:,.2f}")
            col2.metric("Total Current Value", f"₹{total_current:,.2f}")
            col3.metric("Absolute P&L (₹)", f"₹{abs(total_pl):,.2f}", f"₹{total_pl:,.2f}")
            col4.metric("P&L Percentage (%)", f"{abs(total_pl_pct):.2f}%", f"{total_pl_pct:.2f}%")
            st.divider()

        cols = list(merged_df.columns)
        if 'Live Price' in cols and 'Instrument' in cols:
            cols.insert(cols.index('Instrument') + 1, cols.pop(cols.index('Live Price')))
            if 'Day Chg' in cols: cols.insert(cols.index('Live Price') + 1, cols.pop(cols.index('Day Chg')))
        merged_df = merged_df[cols]
        numeric_cols = merged_df.select_dtypes(include=['float64', 'int64']).columns
        merged_df[numeric_cols] = merged_df[numeric_cols].round(2)
        
        st.dataframe(merged_df, use_container_width=True, hide_index=True)

try:
    conn = st.connection("gsheets", type=GSheetsConnection)
    doc = conn.client._client.open_by_url(SPREADSHEET)
    worksheets = doc.worksheets()
    sheet_names = [ws.title for ws in worksheets]
    
    portfolio_sheets = [name for name in sheet_names if name.lower() != 'watchlists']
    
    if portfolio_sheets:
        tabs = st.tabs(portfolio_sheets)
        for tab, sheet_name in zip(tabs, portfolio_sheets):
            with tab:
                holdings_df = conn.read(spreadsheet=SPREADSHEET, worksheet=sheet_name, ttl="5m")
                analyze_and_render_profile(holdings_df, sheet_name)
    else:
        st.warning("No portfolio sheets found. Create a sheet with your holdings.")
                
except Exception as e:
    st.error(f"A critical error occurred while connecting to Google Sheets: {e}")
