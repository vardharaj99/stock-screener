import streamlit as st
import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta
import warnings

warnings.filterwarnings('ignore')

# Set up the web page title and layout
st.set_page_config(page_title="My Portfolio Screener", layout="wide")
st.title("📈 Stage Analysis Portfolio Screener")
st.markdown("Upload your Zerodha holdings CSV to instantly analyze Stage 2 & Stage 4 trends.")

# Create a web file uploader
uploaded_file = st.file_uploader("Upload Zerodha Holdings (CSV)", type="csv")

if uploaded_file is not None:
    try:
        # Read the uploaded CSV
        holdings_df = pd.read_csv(uploaded_file)
        
        if 'Instrument' not in holdings_df.columns:
            st.error("Could not find the 'Instrument' column. Is this a Zerodha file?")
        else:
            raw_tickers = holdings_df['Instrument'].dropna().astype(str).str.strip().tolist()
            tickers = [t + ".NS" if not t.endswith(".NS") else t for t in raw_tickers]
            
            end_date = datetime.today()
            start_date = end_date - timedelta(days=548)
            
            results = []
            
            # Show a loading spinner on the web app while it calculates
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

            if results:
                analysis_df = pd.DataFrame(results)
                merged_df = pd.merge(holdings_df, analysis_df, left_on='Instrument', right_on='Ticker', how='left')
                if 'Ticker' in merged_df.columns: merged_df = merged_df.drop(columns=['Ticker'])
                merged_df = merged_df.loc[:, ~merged_df.columns.str.contains('^Unnamed')]
                
                # Render the final interactive table directly to the web page
                st.success("Analysis Complete!")
                
                # Streamlit's native dataframe handles sorting and rounding beautifully
                st.dataframe(
                    merged_df, 
                    use_container_width=True,
                    hide_index=True
                )
            else:
                st.warning("No valid data could be processed.")
                
    except Exception as e:
        st.error(f"An error occurred: {e}")
