import streamlit as st
import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta
import warnings

warnings.filterwarnings('ignore')

# Set up the web page title and layout
st.set_page_config(page_title="My Portfolio Screener", layout="wide")
st.title("📈 V3: TheWrap TA & Vibe Tracker")
st.markdown("Upload your Zerodha holdings CSV to analyze with Version 3 logic.")

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
            
            # Fetch 2 years to ensure stable EMA calculation and historical cross detection
            end_date = datetime.today()
            start_date = end_date - timedelta(days=730)
            
            results = []
            
            with st.spinner(f"Surgically analyzing {len(tickers)} stocks..."):
                for ticker in tickers:
                    try:
                        df = yf.download(ticker, start=start_date, end=end_date, progress=False)
                        if df.empty or len(df) < 100: continue
                            
                        # Resample to Weekly (Friday) 
                        w = df['Close'].resample('W-FRI').last().to_frame()
                        w['10W_EMA'] = w['Close'].ewm(span=10, adjust=False).mean()
                        w['20W_EMA'] = w['Close'].ewm(span=20, adjust=False).mean()
                        w['40W_EMA'] = w['Close'].ewm(span=40, adjust=False).mean()
                        
                        curr = w.iloc[-1]
                        prev = w.iloc[-2]
                        price = float(curr['Close'])
                        
                        # --- TA Logic Implementation ---
                        action, rationale = "Hold", "Neutral Trend"

                        # 1. Death Cross + 10% Drawdown Rule
                        if curr['10W_EMA'] < curr['40W_EMA']:
                            cross_mask = w['10W_EMA'] < w['40W_EMA']
                            dc_start_date = w[cross_mask].index[-1]
                            dc_price = float(w.loc[dc_start_date, 'Close'])
                            drawdown = ((price - dc_price) / dc_price) * 100
                            
                            if drawdown <= -10:
                                action, rationale = "Sell", f"Exit: {abs(drawdown):.1f}% drop since Death Cross (Anchor: ₹{dc_price:.2f})"
                            else:
                                action, rationale = "Hold", f"Caution: Death Cross active. Buffer intact ({abs(drawdown):.1f}% drawdown)."

                        # 2. Flowchart Convergence logic
                        else:
                            spread_curr = abs(curr['10W_EMA'] - curr['40W_EMA'])
                            spread_prev = abs(prev['10W_EMA'] - prev['40W_EMA'])
                            
                            if spread_curr < spread_prev: # Converging
                                if price < curr['40W_EMA']:
                                    action, rationale = "Sell", "Exit: Price broke support (40W EMA) during convergence."
                                elif price > curr['10W_EMA'] and price > prev['Close']:
                                    action, rationale = "Buy", "Bullish: Breakout from EMA convergence."
                                else:
                                    action, rationale = "Wait", "Wait/Watch: EMAs converging; awaiting breakout."
                            
                            # 3. Standard Trend Logic
                            elif price < curr['40W_EMA']:
                                action, rationale = "Sell", "Exit: Price below 40W EMA."
                            elif price < curr['20W_EMA']:
                                action, rationale = "Hold", "Caution: 20W EMA broken. Watching 40W."
                            elif price > curr['10W_EMA']:
                                action, rationale = "Buy", "Strong Trend: Above all key EMAs."
                            
                        results.append({
                            'Ticker': ticker.replace('.NS', ''), 
                            'Action': action,
                            'Rationale': rationale
                        })
                    except Exception:
                        pass 

            if results:
                analysis_df = pd.DataFrame(results)
                merged_df = pd.merge(holdings_df, analysis_df, left_on='Instrument', right_on='Ticker', how='left')
                if 'Ticker' in merged_df.columns: merged_df = merged_df.drop(columns=['Ticker'])
                
                # Apply color coding
                def color_picker(val):
                    if val == 'Buy': return 'background-color: #29b09d; color: white'
                    if val == 'Sell': return 'background-color: #ff4b4b; color: white'
                    if val == 'Wait': return 'background-color: #ffbd45; color: black'
                    return ''

                st.success("Analysis Complete!")
                
                st.dataframe(
                    merged_df.style.applymap(color_picker, subset=['Action']), 
                    column_config={
                        "Rationale": st.column_config.TextColumn("Rationale ℹ️", help="Based on V3 Flowchart & Death Cross logic."),
                        "Action": st.column_config.TextColumn("Action", width="small")
                    },
                    use_container_width=True,
                    hide_index=True
                )
            else:
                st.warning("No valid data could be processed.")
                
    except Exception as e:
        st.error(f"An error occurred: {e}")
