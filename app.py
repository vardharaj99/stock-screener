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
        # Clean up the ticker names from your CSV and add .NS for Yahoo Finance
        raw_tickers = holdings_df['Instrument'].dropna().astype(str).str.strip().tolist()
        tickers = [t + ".NS" if not t.endswith(".NS") else t for t in raw_tickers]
        
        end_date = datetime.today()
        # Look back 600 days to guarantee we get 50 weeks of trading data
        start_date = end_date - timedelta(days=600) 
        
        results = []
        
        with st.spinner(f"Fetching live prices and analyzing {len(tickers)} stocks... (This may take a minute)"):
            for ticker in tickers:
                try:
                    # Download data from Yahoo Finance silently
                    df = yf.download(ticker, start=start_date, end=end_date, progress=False)
                    
                    if df.empty: 
                        continue
                    
                    # ---------------------------------------------------------
                    # FIX: Safely handle yfinance's new nested table format
                    # ---------------------------------------------------------
                    if isinstance(df.columns, pd.MultiIndex):
                        close_series = df['Close'].iloc[:, 0]
                    else:
                        close_series = df['Close']
                        
                    # Drop blank days
                    close_series = close_series.dropna()
                    
                    # Need at least a few weeks of data to do anything
                    if len(close_series) < 50: 
                        continue
                    
                    # Grab Live Price directly from the most recent tick
                    live_price = float(close_series.iloc[-1])
                        
                    # Resample daily data to weekly data (Fridays)
                    weekly_df = close_series.resample('W-FRI').last()
                    weekly_df = pd.DataFrame(weekly_df, columns=['Close'])
                    
                    # Calculate the 50-Week Simple Moving Average
                    weekly_df['50W_SMA'] = weekly_df['Close'].rolling(window=50).mean()
                    
                    # If the stock is too new to have a 50-week average, skip the analysis
                    if len(weekly_df) < 50 or pd.isna(weekly_df['50W_SMA'].iloc[-1]): 
                        continue
                        
                    current_price = float(weekly_df['Close'].iloc[-1])
                    current_sma = float(weekly_df['50W_SMA'].iloc[-1])
                    sma_4_weeks_ago = float(weekly_df['50W_SMA'].iloc[-5])
                    
                    # Calculate how far the current price is from the moving average
                    pct_distance = ((current_price - current_sma) / current_sma) * 100
                    
                    # Stage Analysis Logic
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
                except Exception:
                    # If one stock fails for some weird reason, ignore it and keep moving
                    pass 

        if results:
            analysis_df = pd.DataFrame(results)
            
            # Merge your original Google Sheet data with the new AI calculations
            merged_df = pd.merge(holdings_df, analysis_df, left_on='Instrument', right_on='Ticker', how='left')
            
            # Clean up duplicate and hidden columns
            if 'Ticker' in merged_df.columns: 
                merged_df = merged_df.drop(columns=['Ticker'])
            merged_df = merged_df.loc[:, ~merged_df.columns.str.contains('^Unnamed')]
            
            # Reorder columns: Move 'Live Price' so it sits right next to 'Instrument'
            cols = list(merged_df.columns)
            if 'Live Price' in cols and 'Instrument' in cols:
                cols.insert(cols.index('Instrument') + 1, cols.pop(cols.index('Live Price')))
                merged_df = merged_df[cols]
            
            # Clean up the math decimals for display
            numeric_cols = merged_df.select_dtypes(include=['float64', 'int64']).columns
            merged_df[numeric_cols] = merged_df[numeric_cols].round(2)
            
            st.success("Live Market Data Pulled Successfully!")
            st.dataframe(merged_df, use_container_width=True, hide_index=True)
        else:
            st.warning("No valid data could be processed. Please check Yahoo Finance connectivity.")
            
except Exception as e:
    st.error(f"An error occurred: {e}")
