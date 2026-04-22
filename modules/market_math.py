import yfinance as yf
import pandas as pd
import numpy as np

def _compute_ema(series, span):
    """Calculates Exponential Moving Average."""
    return series.ewm(span=span, adjust=False).mean()

def _compute_action_and_rationale(weekly_close, live_price):
    """
    Implements TheWrap TA Rules Flowchart unified with EMA metrics.
    
    Logic:
    1. All trend detection uses 10W, 20W, and 40W EMA.
    2. 'Exit' nodes in the flowchart only trigger a 'Sell' if the 
       live price is >= 10% below the 40W EMA.
    """
    wc = weekly_close.dropna()
    if len(wc) < 50:
        return "Hold", "Insufficient data for full TA analysis."

    # Unified EMA Stack
    ema10 = _compute_ema(wc, 10)
    ema20 = _compute_ema(wc, 20)
    ema40 = _compute_ema(wc, 40)

    e10 = float(ema10.iloc[-1])
    e20 = float(ema20.iloc[-1])
    e40 = float(ema40.iloc[-1])

    # Calculate Drawdown from the 40W EMA (Unified Trend Anchor)
    drawdown_from_40w = ((live_price - e40) / e40) * 100

    def _evaluate_exit_node(condition_name):
        """Surgically applies the 10% drawdown rule to flowchart Exit nodes."""
        if drawdown_from_40w <= -10:
            rationale = (
                f"🔴 SELL: {condition_name} met. Price is {abs(drawdown_from_40w):.1f}% "
                f"below the 40W EMA (₹{e40:.2f}), breaching your 10% sustain threshold."
            )
            return "Sell", rationale
        else:
            rationale = (
                f"🟡 WATCH: {condition_name} met, but price is only {abs(drawdown_from_40w):.1f}% "
                f"below 40W EMA. Holding until 10% drawdown threshold is reached."
            )
            return "Hold", rationale

    # EMA Convergence: Gap between 10W and 20W EMA is shrinking
    gap_now = abs(e10 - e20)
    gap_prev = abs(ema10.iloc[-2] - ema20.iloc[-2])
    emas_converging = gap_now < gap_prev

    # Support / Resistance based on recent 20-week swing
    recent = wc.iloc[-20:]
    support = float(recent.min())
    resistance = float(recent.max())

    # --- Flowchart Traversal ---
    if emas_converging:
        if live_price < support:
            return _evaluate_exit_node("Broken Support")
        elif live_price > resistance:
            return "Buy", f"🟢 BUY: Resistance (₹{resistance:.2f}) broken during EMA convergence."
        else:
            return "Hold", "🟡 WAIT: EMAs converging; watching for breakout/breakdown."
    else:
        # EMAs NOT converging
        if live_price < e40:
            return _evaluate_exit_node("Broken 40W EMA")
        elif live_price < e20:
            return "Hold", f"🟡 CAUTIOUS: 20W EMA (₹{e20:.2f}) broken. Trend weakening."
        elif live_price < e10:
            return "Hold", f"🟡 MOMENTUM FADING: 10W EMA (₹{e10:.2f}) broken."
        else:
            return "Buy", "🟢 MAINTAIN: Strong uptrend above all key EMAs (10W/20W/40W)."

def fetch_live_data_and_stage(tickers):
    """Fetches market data and performs unified Stage Analysis using 40W EMA."""
    results = []
    errors = []
    for ticker in tickers:
        try:
            stock = yf.Ticker(ticker)
            df = stock.history(period="2y")

            if df.empty or 'Close' not in df.columns:
                continue

            close_series = df['Close'].dropna()
            
            # Fetch most recent price
            try:
                live_data = stock.history(period="1d", interval="1m")
                live_price = float(live_data['Close'].iloc[-1]) if not live_data.empty else float(close_series.iloc[-1])
            except:
                live_price = float(close_series.iloc[-1])

            # Weekly Resampling for EMA Stack
            weekly_df = close_series.resample('W-FRI').last().to_frame(name='Close')
            weekly_df['40W_EMA'] = _compute_ema(weekly_df['Close'], 40)

            if len(weekly_df) < 40:
                continue

            # Unified Stage Analysis (Based on 40W EMA)
            curr_ema40 = float(weekly_df['40W_EMA'].iloc[-1])
            prev_ema40 = float(weekly_df['40W_EMA'].iloc[-5]) # 4 weeks ago
            pct_dist_ema = ((live_price - curr_ema40) / curr_ema40) * 100

            if live_price > curr_ema40 and curr_ema40 > prev_ema40:
                stage = '🟢 Stage 2 (Uptrend)'
            elif live_price < curr_ema40 and curr_ema40 < prev_ema40:
                stage = '🔴 Stage 4 (Downtrend)'
            else:
                stage = '⚪ Neutral'

            # Action & Rationale
            action, rationale = _compute_action_and_rationale(weekly_df['Close'], live_price)

            results.append({
                'Ticker': ticker.replace('.NS', ''),
                'Live Price': live_price,
                '40W EMA': curr_ema40,
                '% Dist from EMA': pct_dist_ema,
                'Current Stage': stage,
                'Action': action,
                'Rationale': rationale,
            })
        except Exception as e:
            errors.append(f"{ticker}: {str(e)}")
    return results, errors
