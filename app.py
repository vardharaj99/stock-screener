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

try:
    conn = st.connection("gsheets", type=GSheetsConnection)
    holdings_df = conn.read(spreadsheet=SPREADSHEET)
    
    if 'Instrument' not in holdings_df.columns:
        st.error("Could not find the 'Instrument' column. Make sure you imported the full Zerodha CSV into Google Sheets.")
    else:
        raw_tickers = holdings_df['Instrument'].dropna().astype(str).str.strip().tolist()
        tickers = [t + ".NS" if not t.endswith(".NS") else t for t in raw_tickers]
        
        results = []
        errors = [] # <-- New: We will store errors to see exactly what is failing
        
        with st.spinner(f"Fetching live prices and analyzing {len(tickers)} stocks... (This may take a minute)"):
            for ticker in tickers:
                try:
                    # FIX: Use .history() instead of .download() for a stable table format
                    stock = yf.Ticker(ticker)
                    df = stock.history(period="2y")
                    
                    if df.empty or 'Close' not in df.columns: 
                        continue
                    
                    close_series = df['Close'].dropna()
                    
                    # Need at least a few weeks of data
                    if len(close_series) < 50: 
                        continue
                    
                    # Grab Live Price directly
                    live_price = float(close_series.iloc[-1])
                        
                    # Resample to Weekly
                    weekly_df = close_series.resample('W-FRI').last()
                    weekly_df = pd.DataFrame(weekly_df, columns=['Close'])
                    weekly_df['50W_SMA'] = weekly_df['Close'].rolling(window=50).mean()
                    
                    # Skip if stock is too new for a 50-Week average
                    if len(weekly_df) < 50 or pd.isna(weekly_df['50W_SMA'].iloc[-1]): 
                        continue
                        
                    current_price = float(weekly_df['Close'].iloc[-1])
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
                        '50W SMA': current_sma,
                        '% Dist from SMA': pct_distance,
                        'Current Stage': stage
                    })
                except Exception as e:
                    # If it crashes, record the exact error message
                    errors.append(f"{ticker}: {str(e)}") 

        if results:
            analysis_df = pd.DataFrame(results)
            
            merged_df = pd.merge(holdings_df, analysis_df, left_on='Instrument', right_on='Ticker', how='left')
            
            if 'Ticker' in merged_df.columns: 
                merged_df = merged_df.drop(columns=['Ticker'])
            merged_df = merged_df.loc[:, ~merged_df.columns.str.contains('^Unnamed')]
            
            cols = list(merged_df.columns)
            if 'Live Price' in cols and 'Instrument' in cols:
                cols.insert(cols.index('Instrument') + 1, cols.pop(cols.index('Live Price')))
                merged_df = merged_df[cols]
            
            numeric_cols = merged_df.select_dtypes(include=['float64', 'int64']).columns
            merged_df[numeric_cols] = merged_df[numeric_cols].round(2)
            
            st.success("Live Market Data Pulled Successfully!")
            st.dataframe(merged_df, use_container_width=True, hide_index=True)
        else:
            st.warning("No valid data could be processed. Please check Yahoo Finance connectivity.")
            # If everything fails, display the actual errors!
            if errors:
                st.error("Technical debugging details:")
                st.write(errors[:5])
            
except Exception as e:
    st.error(f"An error occurred: {e}")
