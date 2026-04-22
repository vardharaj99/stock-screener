import streamlit as st
import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta
import warnings

warnings.filterwarnings('ignore')

# Set up the web page title and layout
st.set_page_config(page_title="V3 Portfolio Screener", layout="wide")
st.title("📈 V3: TheWrap TA & Vibe Tracker")
st.markdown("Upload your Zerodha holdings to analyze with the **10% Death Cross Rule** and **EMA Convergence** logic.")

def get_v3_signals(ticker_symbol):
    try:
        # Fetch 2 years of data for EMA stability and historical cross detection
        end_date = datetime.today()
        start_date = end_date - timedelta(days=730)
        df = yf.download(ticker_symbol, start=start_date, end=end_date, progress=False)
        
        if df.empty or len(df) < 100:
            return None

        # Resample to Weekly (Friday)
        w = df['Close'].resample('W-FRI').last().to_frame()
        
        # Calculate EMA stack (10W, 20W, 40W)
        w['10W_EMA'] = w['Close'].ewm(span=10, adjust=False).mean()
        w['20W_EMA'] = w['Close'].ewm(span=20, adjust=False).mean()
        w['40W_EMA'] = w['Close'].ewm(span=40, adjust=False).mean()
        
        curr = w.iloc[-1]
        prev = w.iloc[-2]
        price = float(curr['Close'])
        
        # 1. Death Cross Logic (10W < 40W) + 10% Drawdown Rule
        if curr['10W_EMA'] < curr['40W_EMA']:
            # Scan back to find the first week the current Death Cross started
            cross_mask = w['10W_EMA'] < w['40W_EMA']
            # Find the start of the continuous cross sequence
            dc_start_date = w[cross_mask].index[-1]
            dc_price = float(w.loc[dc_start_date, 'Close'])
            drawdown = ((price - dc_price) / dc_price) * 100
            
            if drawdown <= -10:
                return "Sell", f"🔴 Exit: {abs(drawdown):.1f}% drop since Death Cross (Anchor: ₹{dc_price:.2f})"
            return "Hold", f"🟠 Caution: Death Cross active. Drawdown ({abs(drawdown):.1f}%) is within 10% buffer."

        # 2. Flowchart Convergence & Resistance Logic
        spread_curr = abs(curr['10W_EMA'] - curr['40W_EMA'])
        spread_prev = abs(prev['10W_EMA'] - prev['40W_EMA'])
        is_converging = spread_curr < spread_prev
        
        if is_converging:
            if price < curr['40W_EMA']:
                return "Sell", "🔴 Exit: Price broke support (40W EMA) during convergence."
            if price > curr['10W_EMA'] and price > prev['Close']:
                return "Buy", "🟢 Bullish: Breakout seen during EMA convergence."
            return "Wait", "🟡 Watch: EMAs converging; awaiting clear breakout."

        # 3. Standard Trend Following
        if price < curr['40W_EMA']:
            return "Sell", "🔴 Exit: Price broke below the 40W EMA (Long-term trend)."
        if price < curr['20W_EMA']:
            return "Hold", "🟡 Caution: 20W EMA broken. Monitoring 40W support."
        if price < curr['10W_EMA']:
            return "Hold", "🟡 Momentum Fading: 10W EMA broken. Watch 20W."
            
        return "Buy", "🟢 Strong Uptrend: Price maintaining above 10W/20W/40W EMAs."
        
    except Exception:
        return None

# --- UI Logic ---
uploaded_file = st.file_uploader("Upload Zerodha Holdings (CSV)", type="csv")

if uploaded_file is not None:
    try:
        holdings_df = pd.read_csv(uploaded_file)
        if 'Instrument' not in holdings_df.columns:
            st.error("Format Error: 'Instrument' column not found.")
        else:
            raw_tickers = holdings_df['Instrument'].dropna().unique()
            tickers = [t + ".NS" if not t.endswith(".NS") else t for t in raw_tickers]
            
            analysis_results = {}
            with st.spinner(f"Analyzing {len(tickers)} symbols..."):
                for t in tickers:
                    signal = get_v3_signals(t)
                    if signal:
                        analysis_results[t.replace('.NS', '')] = signal

            # Map results back to the original holdings dataframe
            holdings_df['Action'] = holdings_df['Instrument'].map(lambda x: analysis_results.get(x, (None, None))[0])
            holdings_df['Rationale'] = holdings_df['Instrument'].map(lambda x: analysis_results.get(x, (None, None))[1])

            # Drop any rows where we couldn't get technical data
            display_df = holdings_df.dropna(subset=['Action'])

            # Define color coding for the Action column
            def color_picker(val):
                if val == 'Buy': return 'background-color: #29b09d; color: white'
                if val == 'Sell': return 'background-color: #ff4b4b; color: white'
                return 'background-color: #ffbd45; color: black' # Hold/Wait

            st.success("V3 Analysis Complete!")
            
            # Interactive Dataframe with Tooltips
            st.dataframe(
                display_df.style.applymap(color_picker, subset=['Action']),
                column_config={
                    "Rationale": st.column_config.TextColumn(
                        "Rationale ℹ️", 
                        help="Technical justification based on TheWrap TA Rules and Death Cross drawdown."
                    ),
                    "Action": st.column_config.TextColumn("Action", width="small")
                },
                use_container_width=True,
                hide_index=True
            )
            
    except Exception as e:
        st.error(f"Execution Error: {e}")
