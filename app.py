import streamlit as st
from streamlit_gsheets import GSheetsConnection
import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta
import warnings

warnings.filterwarnings('ignore')

st.set_page_config(page_title="My Portfolio Screener", layout="wide")
st.title("📈 Stage Analysis Portfolio Screener")
st.markdown("Fetching securely authenticated portfolio data and **live market prices**...")

# ==========================================
# SECURE CONNECTION URL
# ==========================================
SPREADSHEET = "https://docs.google.com/spreadsheets/d/18ci-lXIJAhb-T96DZ1bL5sEKVmishPTBItIMaACBRJw/edit?gid=0#gid=0"

# ==========================================
# CORE ANALYSIS FUNCTION
# ==========================================
def analyze_and_render_profile(holdings_df, profile_name):
    """Processes the yfinance data and renders the UI for a single portfolio tab."""
    
    if 'Instrument' not in holdings_df.columns:
        st.info(f"Sheet '{profile_name}' is empty or missing the 'Instrument' column. Skipping analysis.")
        return

    raw_tickers = holdings_df['Instrument'].dropna().astype(str).str.strip().tolist()
    if not raw_tickers:
        st.info(f"No tickers found in profile: {profile_name}")
        return
        
    tickers = [t + ".NS" if not t.endswith(".NS") else t for t in raw_tickers]
    results = []
    errors = [] 
    
    with st.spinner(f"Analyzing {len(tickers)} stocks for {profile_name}..."):
        for ticker in tickers:
            try:
                stock = yf.Ticker(ticker)
                
                # 1. Grab Daily History for the Math
                df = stock.history(period="2y")
                
                if df.empty or 'Close' not in df.columns: 
                    continue
                
                close_series = df['Close'].dropna()
                
                if len(close_series) < 50: 
                    continue
                
                # ---------------------------------------------------------
                # Snipe the 1-minute chart for the true Live Price
                # ---------------------------------------------------------
                try:
                    live_data = stock.history(period="1d", interval="1m")
                    if not live_data.empty and 'Close' in live_data.columns:
                        live_price = float(live_data['Close'].dropna().iloc[-1])
                    else:
                        live_price = float(close_series.iloc[-1]) 
                except Exception:
                    live_price = float(close_series.iloc[-1]) 
                
                # Calculate Live Day Change
                if len(close_series) >= 2:
                    prev_close = float(close_series.iloc[-2])
                else:
                    prev_close = live_price
                
                day_chg = ((live_price - prev_close) / prev_close) * 100
                    
                # 2. Do the Stage Analysis Math
                weekly_df = close_series.resample('W-FRI').last()
                weekly_df = pd.DataFrame(weekly_df, columns=['Close'])
                weekly_df['50W_SMA'] = weekly_df['Close'].rolling(window=50).mean()
                
                if len(weekly_df) < 50 or pd.isna(weekly_df['50W_SMA'].iloc[-1]): 
                    continue
                    
                current_price = live_price 
                current_sma = float(weekly_df['50W_SMA'].iloc[-1])
                sma_4_weeks_ago = float(weekly_df['50W_SMA'].iloc[-5])
                pct_distance = ((current_price - current_sma) / current_sma) * 100
                
                if current_price > current_sma and current_sma > sma_4_weeks_ago:
                    stage = '🟢 Stage 2 (Uptrend)'
                elif current_price < current_sma and current_sma < sma_4_weeks_ago:
                    stage = '🔴 Stage 4 (Downtrend)'
                else:
                    stage = '⚪ Neutral'
                    
                results.append({
                    'Ticker': ticker.replace('.NS', ''), 
                    'Live Price': live_price,
                    'Day Chg': day_chg,
                    '50W SMA': current_sma,
                    '% Dist from SMA': pct_distance,
                    'Current Stage': stage
                })
            except Exception as e:
                errors.append(f"{ticker}: {str(e)}") 

    if results:
        analysis_df = pd.DataFrame(results)
        
        merged_df = pd.merge(holdings_df, analysis_df, left_on='Instrument', right_on='Ticker', how='left')
        
        if 'Ticker' in merged_df.columns: 
            merged_df = merged_df.drop(columns=['Ticker'])
        merged_df = merged_df.loc[:, ~merged_df.columns.str.contains('^Unnamed')]

        # ==========================================
        # PORTFOLIO CALCULATIONS & CLEANUP
        # ==========================================
        
        static_cols = ['LTP', 'Day chg.', 'Day Chg.', 'Cur. val', 'Cur. Val', 'P&L', 'Net chg.', 'Net Chg.']
        merged_df = merged_df.drop(columns=[col for col in static_cols if col in merged_df.columns])
        
        if 'Qty.' in merged_df.columns and 'Qty' not in merged_df.columns:
            merged_df = merged_df.rename(columns={'Qty.': 'Qty'})

        if 'Qty' in merged_df.columns:
            merged_df['Qty'] = pd.to_numeric(merged_df['Qty'].astype(str).str.replace(',', ''), errors='coerce')
        if 'Invested' in merged_df.columns:
            merged_df['Invested'] = pd.to_numeric(merged_df['Invested'].astype(str).str.replace(',', ''), errors='coerce')

        if 'Qty' in merged_df.columns and 'Invested' in merged_df.columns:
            merged_df['Cur. Val'] = merged_df['Live Price'] * merged_df['Qty']
            merged_df['P&L'] = merged_df['Cur. Val'] - merged_df['Invested']
            merged_df['Net Chg'] = ((merged_df['Cur. Val'] - merged_df['Invested']) / merged_df['Invested']) * 100

            # ==========================================
            # HEADER METRICS
            # ==========================================
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

        # Reorder columns
        cols = list(merged_df.columns)
        if 'Live Price' in cols and 'Instrument' in cols:
            cols.insert(cols.index('Instrument') + 1, cols.pop(cols.index('Live Price')))
            if 'Day Chg' in cols:
                cols.insert(cols.index('Live Price') + 1, cols.pop(cols.index('Day Chg')))
        merged_df = merged_df[cols]
        
        numeric_cols = merged_df.select_dtypes(include=['float64', 'int64']).columns
        merged_df[numeric_cols] = merged_df[numeric_cols].round(2)
        
        st.dataframe(merged_df, use_container_width=True, hide_index=True)
    else:
        st.warning(f"No valid data could be processed for {profile_name}.")
        if errors:
            with st.expander("View technical errors"):
                st.write(errors)

# ==========================================
# MAIN APP EXECUTION
# ==========================================
try:
    conn = st.connection("gsheets", type=GSheetsConnection)
    
    # 1. Access the underlying gspread client to fetch all sheet names
    doc = conn.client._client.open_by_url(SPREADSHEET)
    worksheets = doc.worksheets()
    sheet_names = [ws.title for ws in worksheets]
    
    if not sheet_names:
        st.error("No sheets found in the Google Spreadsheet.")
    else:
        # 2. Dynamically create Streamlit tabs based on the sheet names
        tabs = st.tabs(sheet_names)
        
        # 3. Loop through each tab and execute our analysis function
        for tab, sheet_name in zip(tabs, sheet_names):
            with tab:
                # Read the specific worksheet. Note the ttl="5m" to auto-refresh cache!
                holdings_df = conn.read(spreadsheet=SPREADSHEET, worksheet=sheet_name, ttl="5m")
                analyze_and_render_profile(holdings_df, sheet_name)
                
except Exception as e:
    st.error(f"A critical error occurred while connecting to Google Sheets: {e}")
