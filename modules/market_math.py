import yfinance as yf
import pandas as pd

def fetch_live_data_and_stage(tickers):
    """Reusable function to fetch live prices and calculate stage analysis."""
    results = []
    errors = []
    for ticker in tickers:
        try:
            stock = yf.Ticker(ticker)
            df = stock.history(period="2y")
            
            if df.empty or 'Close' not in df.columns: 
                continue
            
            close_series = df['Close'].dropna()
            if len(close_series) < 50: 
                continue
            
            # Snipe 1-minute chart for Live Price
            try:
                live_data = stock.history(period="1d", interval="1m")
                if not live_data.empty and 'Close' in live_data.columns:
                    live_price = float(live_data['Close'].dropna().iloc[-1])
                else:
                    live_price = float(close_series.iloc[-1]) 
            except Exception:
                live_price = float(close_series.iloc[-1]) 
            
            # Day Change
            if len(close_series) >= 2:
                prev_close = float(close_series.iloc[-2])
            else:
                prev_close = live_price
            day_chg = ((live_price - prev_close) / prev_close) * 100
                
            # Stage Analysis
            weekly_df = close_series.resample('W-FRI').last()
            weekly_df = pd.DataFrame(weekly_df, columns=['Close'])
            weekly_df['50W_SMA'] = weekly_df['Close'].rolling(window=50).mean()
            
            if len(weekly_df) < 50 or pd.isna(weekly_df['50W_SMA'].iloc[-1]): 
                continue
                
            current_sma = float(weekly_df['50W_SMA'].iloc[-1])
            sma_4_weeks_ago = float(weekly_df['50W_SMA'].iloc[-5])
            pct_distance = ((live_price - current_sma) / current_sma) * 100
            
            if live_price > current_sma and current_sma > sma_4_weeks_ago:
                stage = '🟢 Stage 2 (Uptrend)'
            elif live_price < current_sma and current_sma < sma_4_weeks_ago:
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
    return results, errors
