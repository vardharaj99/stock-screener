import yfinance as yf
import pandas as pd
import numpy as np


def _compute_ema(series, span):
    return series.ewm(span=span, adjust=False).mean()


def _compute_action_and_rationale(weekly_close, live_price):
    """
    Implements TheWrap TA Rules Flowchart with 5% confirmation buffer on Exit signals.

    Flowchart:
    1. Are EMAs converging?
       YES -> Has it broken support (price < support * 0.95)?
               YES -> SELL
               NO  -> Has it broken resistance?
                       YES -> BUY (Bullish Signal)
                       NO  -> HOLD (Wait/Watch)
       NO  -> Has it broken 40W EMA (price < 40W EMA * 0.95)?
               YES -> SELL
               NO  -> Has it broken 20W EMA?
                       YES -> HOLD (Be Cautious)
                       NO  -> Has it broken 10W EMA?
                               YES -> HOLD (Momentum Fading)
                               NO  -> BUY (Maintain Position / Add)
    """
    wc = weekly_close.dropna()
    if len(wc) < 50:
        return "Hold", "Insufficient data for full TA analysis. Defaulting to Hold."

    ema10 = _compute_ema(wc, 10)
    ema20 = _compute_ema(wc, 20)
    ema40 = _compute_ema(wc, 40)

    e10 = float(ema10.iloc[-1])
    e20 = float(ema20.iloc[-1])
    e40 = float(ema40.iloc[-1])

    e10_prev = float(ema10.iloc[-2]) if len(ema10) > 1 else e10
    e20_prev = float(ema20.iloc[-2]) if len(ema20) > 1 else e20

    # --- EMA convergence: gap between 10W and 20W EMA is shrinking ---
    gap_now  = abs(e10 - e20)
    gap_prev = abs(e10_prev - e20_prev)
    emas_converging = gap_now < gap_prev

    # --- Support / Resistance: 20-week swing low / high ---
    recent = wc.iloc[-20:]
    support    = float(recent.min())
    resistance = float(recent.max())

    # Exit triggers: 5% confirmed break below the structural level
    BUFFER = 0.95
    sell_support    = live_price < support * BUFFER
    sell_40w        = live_price < e40 * BUFFER

    # Regular EMA breaks (no buffer — these are Hold signals, not Sell)
    broken_resistance = live_price > resistance * 0.99
    broken_20w        = live_price < e20
    broken_10w        = live_price < e10

    # pct below trigger — for rationale clarity
    def _pct_below(price, level):
        return ((level - price) / level) * 100

    # ---- FLOWCHART TRAVERSAL ----
    if emas_converging:
        if sell_support:
            pct = _pct_below(live_price, support)
            rationale = (
                f"EMAs CONVERGING but price has broken support (₹{support:.2f}) "
                f"with a confirmed {pct:.1f}% decline below it (5% buffer breached). "
                f"EXIT signal per TheWrap TA Rules. "
                f"10W EMA: ₹{e10:.2f} | 20W EMA: ₹{e20:.2f} | Live: ₹{live_price:.2f}."
            )
            return "Sell", rationale

        elif broken_resistance:
            rationale = (
                f"EMAs CONVERGING and price has broken above resistance (₹{resistance:.2f}). "
                f"Bullish Signal per TheWrap TA Rules. "
                f"10W EMA: ₹{e10:.2f} | 20W EMA: ₹{e20:.2f} | Live: ₹{live_price:.2f}."
            )
            return "Buy", rationale

        else:
            pct_to_support    = ((live_price - support) / support) * 100
            pct_to_resistance = ((resistance - live_price) / live_price) * 100
            rationale = (
                f"EMAs CONVERGING. Support (₹{support:.2f}) intact — "
                f"price is {pct_to_support:.1f}% above support. "
                f"Resistance at ₹{resistance:.2f} ({pct_to_resistance:.1f}% away). "
                f"Wait/Watch for a breakout. "
                f"10W EMA: ₹{e10:.2f} | 20W EMA: ₹{e20:.2f} | Live: ₹{live_price:.2f}."
            )
            return "Hold", rationale

    else:
        # EMAs NOT converging
        if sell_40w:
            pct = _pct_below(live_price, e40)
            rationale = (
                f"EMAs DIVERGING and price has broken below the 40W EMA (₹{e40:.2f}) "
                f"with a confirmed {pct:.1f}% decline below it (5% buffer breached). "
                f"EXIT signal per TheWrap TA Rules. "
                f"10W EMA: ₹{e10:.2f} | 20W EMA: ₹{e20:.2f} | Live: ₹{live_price:.2f}."
            )
            return "Sell", rationale

        elif broken_20w:
            pct = _pct_below(live_price, e20)
            rationale = (
                f"EMAs DIVERGING and price has broken below the 20W EMA (₹{e20:.2f}) "
                f"by {pct:.1f}% — but still above the 40W EMA (₹{e40:.2f}). "
                f"Be Cautious, momentum is weakening. "
                f"10W EMA: ₹{e10:.2f} | Live: ₹{live_price:.2f}."
            )
            return "Hold", rationale

        elif broken_10w:
            pct = _pct_below(live_price, e10)
            rationale = (
                f"EMAs DIVERGING and price has broken below the 10W EMA (₹{e10:.2f}) "
                f"by {pct:.1f}% — 20W EMA (₹{e20:.2f}) and 40W EMA (₹{e40:.2f}) still hold. "
                f"Momentum Fading — watch closely. Live: ₹{live_price:.2f}."
            )
            return "Hold", rationale

        else:
            rationale = (
                f"EMAs DIVERGING but price is ABOVE all key EMAs: "
                f"10W ₹{e10:.2f} | 20W ₹{e20:.2f} | 40W ₹{e40:.2f}. "
                f"Maintain Position / Add. Live: ₹{live_price:.2f}."
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

            # Stage Analysis (50W SMA)
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
