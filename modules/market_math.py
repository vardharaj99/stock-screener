import yfinance as yf
import pandas as pd
import numpy as np


def _compute_ema(series, span):
    return series.ewm(span=span, adjust=False).mean()


def _compute_action_and_rationale(weekly_close, live_price):
    """
    Implements TheWrap TA Rules Flowchart.
    Returns (action, rationale) where action is 'Buy', 'Sell', or 'Hold'.

    Flowchart logic:
    1. Are EMAs converging?
       YES → Has it broken support?
               YES → Exit  (but SELL only if 10% drawdown from death cross; else Hold)
               NO  → Has it broken resistance?
                       YES → Bullish Signal → BUY
                       NO  → Wait/Watch     → HOLD
       NO  → Has it broken 40W EMA?
               YES → Exit  (SELL if 10% drawdown from death cross; else Hold)
               NO  → Has it broken 20W EMA?
                       YES → Be Cautious → HOLD
                       NO  → Has it broken 10W EMA?
                               YES → Momentum Fading → HOLD
                               NO  → Maintain Position / Add → BUY
    """
    wc = weekly_close.dropna()
    if len(wc) < 50:
        return "Hold", "Insufficient data for full TA analysis. Defaulting to Hold."

    ema10 = _compute_ema(wc, 10)
    ema20 = _compute_ema(wc, 20)
    ema40 = _compute_ema(wc, 40)
    ema50 = _compute_ema(wc, 50)

    e10 = float(ema10.iloc[-1])
    e20 = float(ema20.iloc[-1])
    e40 = float(ema40.iloc[-1])
    e50 = float(ema50.iloc[-1])

    e10_prev = float(ema10.iloc[-2]) if len(ema10) > 1 else e10
    e20_prev = float(ema20.iloc[-2]) if len(ema20) > 1 else e20

    # --- EMA convergence: 10W EMA and 20W EMA are moving toward each other ---
    gap_now  = abs(e10 - e20)
    gap_prev = abs(e10_prev - e20_prev)
    emas_converging = gap_now < gap_prev

    # --- Death cross: 10W EMA crossed below 20W EMA ---
    death_cross = (e10 < e20) and (e10_prev >= e20_prev)
    # For drawdown check: find price at death cross moment
    # Use rolling: find last bar where ema10 crossed below ema20
    cross_mask = (ema10 < ema20) & (ema10.shift(1) >= ema20.shift(1))
    drawdown_pct = None
    if cross_mask.any():
        last_cross_idx = cross_mask[cross_mask].index[-1]
        price_at_cross = float(wc.loc[last_cross_idx]) if last_cross_idx in wc.index else None
        if price_at_cross and price_at_cross > 0:
            drawdown_pct = ((live_price - price_at_cross) / price_at_cross) * 100

    def _sell_or_hold_on_exit():
        """SELL only if ≥10% drawdown from a death cross has occurred."""
        if drawdown_pct is not None and drawdown_pct <= -10:
            rationale = (
                f"EXIT SIGNAL triggered. A Death Cross (10W EMA crossed below 20W EMA) "
                f"occurred, and the stock has since fallen {abs(drawdown_pct):.1f}% from that "
                f"level — exceeding the 10% drawdown threshold. "
                f"10W EMA: ₹{e10:.2f} | 20W EMA: ₹{e20:.2f} | "
                f"40W EMA: ₹{e40:.2f} | Live: ₹{live_price:.2f}."
            )
            return "Sell", rationale
        else:
            dd_str = f"{drawdown_pct:.1f}%" if drawdown_pct is not None else "N/A"
            rationale = (
                f"Exit condition partially met (EMAs signalling weakness), but the 10% "
                f"drawdown from Death Cross threshold has NOT been breached "
                f"(current drawdown from cross: {dd_str}). Holding for now. "
                f"10W EMA: ₹{e10:.2f} | 20W EMA: ₹{e20:.2f} | Live: ₹{live_price:.2f}."
            )
            return "Hold", rationale

    # --- Support / Resistance: use recent swing lows/highs over last 20 weeks ---
    recent = wc.iloc[-20:]
    support    = float(recent.min())
    resistance = float(recent.max())
    broken_support    = live_price < support * 0.99   # 1% buffer
    broken_resistance = live_price > resistance * 0.99

    # --- EMA breaks ---
    broken_40w = live_price < e40
    broken_20w = live_price < e20
    broken_10w = live_price < e10

    # ---- FLOWCHART TRAVERSAL ----
    if emas_converging:
        if broken_support:
            return _sell_or_hold_on_exit()
        else:
            if broken_resistance:
                rationale = (
                    f"EMAs are CONVERGING and price has broken above resistance (₹{resistance:.2f}). "
                    f"This is a Bullish Signal per TheWrap TA Rules. "
                    f"10W EMA: ₹{e10:.2f} | 20W EMA: ₹{e20:.2f} | Live: ₹{live_price:.2f}."
                )
                return "Buy", rationale
            else:
                rationale = (
                    f"EMAs are CONVERGING but price has not yet broken resistance (₹{resistance:.2f}). "
                    f"Support (₹{support:.2f}) is intact. Wait/Watch for a breakout. "
                    f"10W EMA: ₹{e10:.2f} | 20W EMA: ₹{e20:.2f} | Live: ₹{live_price:.2f}."
                )
                return "Hold", rationale
    else:
        # EMAs NOT converging
        if broken_40w:
            return _sell_or_hold_on_exit()
        else:
            if broken_20w:
                rationale = (
                    f"EMAs are DIVERGING and price has broken below the 20W EMA (₹{e20:.2f}). "
                    f"40W EMA (₹{e40:.2f}) still holds. Be Cautious — momentum is weakening. "
                    f"10W EMA: ₹{e10:.2f} | Live: ₹{live_price:.2f}."
                )
                return "Hold", rationale
            else:
                if broken_10w:
                    rationale = (
                        f"EMAs are DIVERGING and price has broken below the 10W EMA (₹{e10:.2f}), "
                        f"but 20W EMA (₹{e20:.2f}) and 40W EMA (₹{e40:.2f}) still hold. "
                        f"Momentum is Fading — watch closely. Live: ₹{live_price:.2f}."
                    )
                    return "Hold", rationale
                else:
                    rationale = (
                        f"EMAs are DIVERGING but price is ABOVE all key EMAs: "
                        f"10W ₹{e10:.2f} | 20W ₹{e20:.2f} | 40W ₹{e40:.2f}. "
                        f"No EMA broken. Signal: Maintain Position / Add. Live: ₹{live_price:.2f}."
                    )
                    return "Buy", rationale


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

            # Action & Rationale (TheWrap TA Flowchart)
            weekly_close = weekly_df['Close']
            action, rationale = _compute_action_and_rationale(weekly_close, live_price)
                
            results.append({
                'Ticker': ticker.replace('.NS', ''), 
                'Live Price': live_price,
                'Day Chg': day_chg,
                '50W SMA': current_sma,
                '% Dist from SMA': pct_distance,
                'Current Stage': stage,
                'Action': action,
                'Rationale': rationale,
            })
        except Exception as e:
            errors.append(f"{ticker}: {str(e)}") 
    return results, errors
