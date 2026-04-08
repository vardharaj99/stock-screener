import streamlit as st
from streamlit_gsheets import GSheetsConnection
import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta
import warnings

warnings.filterwarnings('ignore')

st.set_page_config(page_title="My Portfolio Screener", layout="wide")
st.title("📈 Stage Analysis Portfolio Screener")
st.markdown("Fetching live, securely authenticated portfolio data...")

# ==========================================
# SECURE CONNECTION URL
# Using the full URL that successfully bypassed the cache!
# ==========================================
SPREADSHEET = "https://docs.google.com/spreadsheets/d/18ci-lXIJAhb-T96DZ1bL5sEKVmishPTBItIMaACBRJw/edit?gid=0#gid=0"

try:
    # 1. Connect securely using the hidden secrets
    conn = st.connection("gsheets", type=GSheetsConnection)
    
    # 2. Read the data (using the full URL variable)
    holdings_df = conn.read(spreadsheet=SPREADSHEET)
    
    if 'Instrument' not in holdings_df.columns:
        st.error("Could not find the 'Instrument' column. Make sure you imported the full Zerodha CSV into Google Sheets.")
    else:
        raw_tickers = holdings_df['Instrument'].dropna().astype(str).str.strip().tolist()
        tickers = [t + ".NS" if not t.endswith(".NS") else t for t in raw_tickers]
        
        end_date = datetime.today()
        start_date = end_date - timedelta(days=548)
        
        results = []
        
        # 3. Analyze the stocks using yfinance
        with st.spinner(f"Analyzing {len(tickers)} stocks..."):
            for ticker in tickers:
                try:
                    df = yf.download(ticker, start=start_date, end=end_date, progress=False)
                    if df.empty or len(df) < 250: continue
                        
                    weekly_df = df['Close'].resample('W-FRI').last()
                    weekly_df = pd.DataFrame(weekly_df)
                    weekly_df.columns = ['Close']
                    weekly_df['50W_SMA'] = weekly_df['Close'].rolling(window=50).mean()
                    
                    if pd.isna(weekly_df['50W_SMA'].iloc[-1]) or len(weekly_df) < 55: continue
                        
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
                        '50W SMA': current_sma,
                        '% Dist from SMA': pct_distance,
                        'Current Stage': stage
                    })
                except Exception:
                    pass 

        # 4. Merge and display the final results
        if results:
            analysis_df = pd.DataFrame(results)
            
            # Merge to keep ALL original Zerodha columns
            merged_df = pd.merge(holdings_df, analysis_df, left_on='Instrument', right_on='Ticker', how='left')
            
            # Clean up duplicate Ticker column and any hidden 'Unnamed' columns
            if 'Ticker' in merged_df.columns: 
                merged_df = merged_df.drop(columns=['Ticker'])
            merged_df = merged_df.loc[:, ~merged_df.columns.str.contains('^Unnamed')]
            
            # Round off numeric columns for a clean display
            numeric_cols = merged_df.select_dtypes(include=['float64', 'int64']).columns
            merged_df[numeric_cols] = merged_df[numeric_cols].round(0)
            
            st.success("Analysis Complete!")
            st.dataframe(merged_df, use_container_width=True, hide_index=True)
        else:
            st.warning("No valid data could be processed.")
            
except Exception as e:
    st.error(f"An error occurred: {e}")
