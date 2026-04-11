import streamlit as st
import pandas as pd
from googleapiclient.discovery import build
from modules.google_auth import get_fresh_creds, get_user_spreadsheet_id
from modules.market_math import fetch_live_data_and_stage
from streamlit_searchbox import st_searchbox
import requests
import warnings
import datetime

warnings.filterwarnings('ignore')

st.set_page_config(page_title="Portfolio", page_icon="💼", layout="wide")

try:
    creds   = get_fresh_creds()
    ss_id   = get_user_spreadsheet_id(creds)
    service = build('sheets', 'v4', credentials=creds)
except Exception as e:
    st.error(f"Failed to connect to your private database: {e}")
    st.stop()

if "show_portfolio_add" not in st.session_state:
    st.session_state.show_portfolio_add = False

def ensure_portfolio_sheet():
    meta = service.spreadsheets().get(spreadsheetId=ss_id).execute()
    existing = [s['properties']['title'] for s in meta.get('sheets', [])]
    if 'Portfolio' not in existing:
        service.spreadsheets().batchUpdate(
            spreadsheetId=ss_id,
            body={'requests': [{'addSheet': {'properties': {'title': 'Portfolio'}}}]}
        ).execute()
        headers = [["Instrument", "Exchange", "Qty", "Avg Buy Price", "Buy Date", "Sector", "Notes"]]
        service.spreadsheets().values().update(
            spreadsheetId=ss_id, range="Portfolio!A1",
            valueInputOption="RAW", body={'values': headers},
        ).execute()

ensure_portfolio_sheet()

PORTFOLIO_COLS = ["Instrument", "Exchange", "Qty", "Avg Buy Price", "Buy Date", "Sector", "Notes"]

def get_portfolio_data():
    try:
        result = service.spreadsheets().values().get(
            spreadsheetId=ss_id, range="Portfolio!A:G",
        ).execute()
        values = result.get('values', [])
        if not values or len(values) < 2:
            return pd.DataFrame(columns=PORTFOLIO_COLS)
        df = pd.DataFrame(values[1:], columns=values[0])
        for col in PORTFOLIO_COLS:
            if col not in df.columns:
                df[col] = ''
        return df[PORTFOLIO_COLS]
    except Exception:
        return pd.DataFrame(columns=PORTFOLIO_COLS)

def save_portfolio(df):
    service.spreadsheets().values().clear(
        spreadsheetId=ss_id, range="Portfolio!A:G"
    ).execute()
    body = {'values': [df.columns.tolist()] + df.fillna('').values.tolist()}
    service.spreadsheets().values().update(
        spreadsheetId=ss_id, range="Portfolio!A1",
        valueInputOption="RAW", body=body,
    ).execute()

def search_yahoo_finance(searchterm: str):
    if not searchterm or len(searchterm) < 2:
        return []
    url = f"https://query2.finance.yahoo.com/v1/finance/search?q={searchterm}&quotesCount=10"
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        resp = requests.get(url, headers=headers, timeout=8).json()
        return [
            (f"{q.get('shortname')} ({q.get('symbol')})", q.get('symbol'))
            for q in resp.get('quotes', [])
            if ('.NS' in q.get('symbol', '') or '.BO' in q.get('symbol', ''))
        ]
    except Exception:
        return []

portfolio_df = get_portfolio_data()

col_hdr, col_btn = st.columns([0.8, 0.2], vertical_alignment="bottom")
col_hdr.markdown("### 💼 Portfolio")
user_email = st.session_state.get("user_email", "authenticated user")
col_hdr.caption(f"Authenticated as: {user_email} | DB: StockScreener_DB")

if col_btn.button("➕ Add Holding", type="primary", use_container_width=True):
    st.session_state.show_portfolio_add = not st.session_state.show_portfolio_add
    st.rerun()

if st.session_state.show_portfolio_add:
    with st.container(border=True):
        st.markdown("#### ⚙️ Add New Holding")
        c1, c2, c3, c4 = st.columns(4)
        ticker   = st_searchbox(search_yahoo_finance, key="p_src", label="Search Ticker")
        qty      = c2.number_input("Qty", min_value=1, step=1, value=1)
        buy_date = c3.date_input("Buy Date", value=datetime.date.today())
        sector   = c4.text_input("Sector (optional)")
        notes    = st.text_input("Notes (optional)")

        a1, a2 = st.columns([0.8, 0.2])
        if a1.button("➕ Save Holding", type="primary", use_container_width=True):
            if ticker:
                with st.spinner("Fetching buy price..."):
                    try:
                        import yfinance as yf
                        tk = yf.Ticker(ticker)
                        h  = tk.history(
                            start=buy_date.strftime("%Y-%m-%d"),
                            end=(buy_date + datetime.timedelta(days=7)).strftime("%Y-%m-%d"),
                        )
                        if not h.empty:
                            avg_price  = float(h['Close'].iloc[0])
                            instrument = ticker.replace('.NS', '').replace('.BO', '').upper()
                            exchange   = 'NSE' if '.NS' in ticker else 'BSE'
                            new_row = pd.DataFrame([[
                                instrument, exchange, int(qty), round(avg_price, 2),
                                h.index[0].strftime("%Y-%m-%d"), sector, notes
                            ]], columns=PORTFOLIO_COLS)
                            updated = pd.concat([portfolio_df, new_row], ignore_index=True)
                            save_portfolio(updated)
                            st.success(f"Added {instrument} × {qty} @ ₹{avg_price:.2f}")
                            st.session_state.show_portfolio_add = False
                            st.rerun()
                        else:
                            st.warning("No price data for that date. Try a trading day.")
                    except Exception as e:
                        st.error(f"Error: {e}")
            else:
                st.warning("Please select a ticker first.")

        if a2.button("Cancel", use_container_width=True):
            st.session_state.show_portfolio_add = False
            st.rerun()

st.divider()

if portfolio_df.empty or portfolio_df['Instrument'].replace('', pd.NA).dropna().empty:
    st.info("Your portfolio is empty. Click 'Add Holding' to get started!")
    st.stop()

portfolio_df['Qty']           = pd.to_numeric(portfolio_df['Qty'],           errors='coerce').fillna(0)
portfolio_df['Avg Buy Price'] = pd.to_numeric(portfolio_df['Avg Buy Price'], errors='coerce').fillna(0)

portfolio_df['_ticker_yf'] = portfolio_df.apply(
    lambda r: r['Instrument'] + ('.NS' if r.get('Exchange', 'NSE') == 'NSE' else '.BO'), axis=1
)
tickers_yf = portfolio_df['_ticker_yf'].tolist()

with st.spinner("Fetching live prices..."):
    results, errors = fetch_live_data_and_stage(tickers_yf)

if not results:
    st.warning("Could not fetch live market data. Showing cost basis only.")
    st.dataframe(portfolio_df.drop(columns=['_ticker_yf']), use_container_width=True, hide_index=True)
    st.stop()

analysis_df = pd.DataFrame(results)
merged = pd.merge(portfolio_df, analysis_df, left_on='Instrument', right_on='Ticker', how='left')

merged['Cost Basis'] = (merged['Avg Buy Price'] * merged['Qty']).round(2)
merged['Cur. Val']   = (merged['Live Price']    * merged['Qty']).round(2)
merged['P&L (₹)']   = (merged['Cur. Val'] - merged['Cost Basis']).round(2)
merged['P&L (%)']   = ((merged['P&L (₹)'] / merged['Cost Basis']) * 100).round(2)

def trend(val):
    if pd.isna(val): return '⚪ –'
    return '🟢 Profit' if val > 0 else '🔴 Loss' if val < 0 else '⚪ Flat'

merged['Trend'] = merged['P&L (₹)'].apply(trend)
merged['Chart'] = (
    "https://www.screener.in/company/"
    + merged['Instrument'].str.replace('.NS', '').str.replace('.BO', '')
    + "/"
)
merged['🗑️ Delete'] = False

total_invested = merged['Cost Basis'].sum()
total_current  = merged['Cur. Val'].sum()
total_pnl      = total_current - total_invested
total_pnl_pct  = (total_pnl / total_invested * 100) if total_invested > 0 else 0
winners        = (merged['P&L (₹)'] > 0).sum()
losers         = (merged['P&L (₹)'] < 0).sum()

m1, m2, m3, m4, m5 = st.columns(5)
m1.metric("Total Invested", f"₹{total_invested:,.0f}")
m2.metric("Current Value",  f"₹{total_current:,.0f}")
m3.metric("Overall P&L",    f"₹{total_pnl:,.0f}", f"{total_pnl_pct:.2f}%")
m4.metric("Winners 🟢",     str(winners))
m5.metric("Losers 🔴",      str(losers))

st.divider()

display_cols = [
    'Instrument', 'Exchange', 'Qty', 'Avg Buy Price', 'Live Price',
    'Cost Basis', 'Cur. Val', 'P&L (₹)', 'P&L (%)', 'Trend',
    'Current Stage', 'Day Chg', '50W SMA', '% Dist from SMA',
    'Buy Date', 'Sector', 'Notes', 'Chart', '🗑️ Delete',
]
final_df = merged[[c for c in display_cols if c in merged.columns]]

edited_df = st.data_editor(
    final_df,
    key="portfolio_editor",
    use_container_width=True,
    hide_index=True,
    disabled=[c for c in final_df.columns if c not in ('🗑️ Delete',)],
    column_config={
        "Chart":   st.column_config.LinkColumn("Chart", display_text="📈 View"),
        "P&L (%)": st.column_config.NumberColumn("P&L (%)", format="%.2f%%"),
        "Day Chg": st.column_config.NumberColumn("Day Chg", format="%.2f%%"),
    },
)

if edited_df['🗑️ Delete'].any():
    if st.button("🗑️ Confirm Deletion", key="del_portfolio", type="primary"):
        to_keep = edited_df[edited_df['🗑️ Delete'] == False]['Instrument'].tolist()
        new_df  = portfolio_df[portfolio_df['Instrument'].isin(to_keep)].drop(columns=['_ticker_yf'])
        save_portfolio(new_df)
        st.rerun()

if 'Sector' in merged.columns and merged['Sector'].replace('', pd.NA).dropna().any():
    st.divider()
    st.markdown("#### 🏭 Sector Breakdown")
    sector_df = (
        merged[merged['Sector'] != '']
        .groupby('Sector')
        .agg(Holdings=('Instrument', 'count'), Invested=('Cost Basis', 'sum'), Value=('Cur. Val', 'sum'))
        .reset_index()
    )
    sector_df['P&L (₹)'] = (sector_df['Value'] - sector_df['Invested']).round(2)
    sector_df['P&L (%)'] = ((sector_df['P&L (₹)'] / sector_df['Invested']) * 100).round(2)
    st.dataframe(sector_df, use_container_width=True, hide_index=True)
