import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import warnings
from modules.market_math import fetch_live_data_and_stage

warnings.filterwarnings('ignore')

st.set_page_config(page_title="Paper Trading", page_icon="👀", layout="wide")
st.title("👀 Paper Trading Watchlists")
st.markdown("Track hypothetical entry points based on Stage Analysis.")

SPREADSHEET = "https://docs.google.com/spreadsheets/d/18ci-lXIJAhb-T96DZ1bL5sEKVmishPTBItIMaACBRJw/edit?gid=0#gid=0"

# A starter list of popular stocks for the type-ahead search. 
# You can expand this list as much as you want!
POPULAR_STOCKS = [
    "RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "ICICIBANK.NS", "BHARTIARTL.NS", 
    "SBI.NS", "INFY.NS", "LITC.NS", "HINDUNILVR.NS", "ITC.NS", "LT.NS",
    "BAJFINANCE.NS", "HCLTECH.NS", "MARUTI.NS", "SUNPHARMA.NS", "TATAMOTORS.NS",
    "MAHINDRA.NS", "TATASTEEL.NS", "KOTAKBANK.NS", "AXISBANK.NS", "HAL.NS",
    "NATCOPHARM.NS", "KOPRAN.NS", "SANSERA.NS", "BEL.NS", "ZOMATO.NS"
]

def analyze_and_render_watchlists(watchlist_df):
    required_cols = ['List Name', 'Instrument', 'Date Added', 'Price Added']
    if not all(col in watchlist_df.columns for col in required_cols):
        st.error(f"Watchlist sheet is missing columns. It must exactly have: {', '.join(required_cols)}")
        return

    list_names = [name for name in watchlist_df['List Name'].unique() if pd.notnull(name) and str(name).strip() != '']
    
    if len(list_names) == 0:
        return

    tabs = st.tabs(list_names)
    for tab, current_list in zip(tabs, list_names):
        with tab:
            df = watchlist_df[watchlist_df['List Name'] == current_list].copy()
            
            raw_tickers = [str(t).strip() for t in df['Instrument'].tolist() if pd.notnull(t)]
            tickers = [t + ".NS" if not t.endswith(".NS") else t for t in raw_tickers]
            
            with st.spinner(f"Fetching live data for {current_list} watchlist..."):
                results, errors = fetch_live_data_and_stage(tickers)
            
            if results:
                analysis_df = pd.DataFrame(results)
                merged_df = pd.merge(df, analysis_df, left_on='Instrument', right_on='Ticker', how='left')
                if 'Ticker' in merged_df.columns: merged_df = merged_df.drop(columns=['Ticker'])
                
                def clean_price(val):
                    try:
                        return float(str(val).replace(',', '').strip())
                    except:
                        return 0.0
                
                merged_df['Price Added'] = merged_df['Price Added'].apply(clean_price)
                merged_df['Hypo. P&L'] = merged_df['Live Price'] - merged_df['Price Added']
                merged_df['Hypo. Net Chg (%)'] = (merged_df['Hypo. P&L'] / merged_df['Price Added']) * 100
                
                def get_trend_indicator(val):
                    try:
                        v = float(val)
                        if v > 0: return '🟢 Profit'
                        elif v < 0: return '🔴 Loss'
                    except:
                        pass
                    return '⚪ Flat'
                
                merged_df['Trend'] = merged_df['Hypo. P&L'].apply(get_trend_indicator)
                merged_df['Chart'] = "https://www.screener.in/company/" + merged_df['Instrument'] + "/"

                cols = ['Instrument', 'Chart', 'List Name', 'Date Added', 'Price Added', 'Live Price', 'Trend', 'Hypo. P&L', 'Hypo. Net Chg (%)', 'Current Stage', 'Day Chg', '50W SMA', '% Dist from SMA']
                merged_df = merged_df[[c for c in cols if c in merged_df.columns]]
                
                numeric_cols = merged_df.select_dtypes(include=['float64', 'int64']).columns
                merged_df[numeric_cols] = merged_df[numeric_cols].round(2)
                
                st.dataframe(
                    merged_df, 
                    use_container_width=True, 
                    hide_index=True,
                    column_config={
                        "Chart": st.column_config.LinkColumn("Chart", help="Click to open Screener.in", display_text="📈 View")
                    }
                )
            else:
                st.warning("Could not fetch data for this list.")

try:
    conn = st.connection("gsheets", type=GSheetsConnection)
    doc = conn.client._client.open_by_url(SPREADSHEET)
    
    try:
        ws_watchlists = doc.worksheet("Watchlists")
    except Exception:
        ws_watchlists = doc.add_worksheet(title="Watchlists", rows="100", cols="20")
        ws_watchlists.append_row(["List Name", "Instrument", "Date Added", "Price Added"])
    
    raw_watchlist_df = conn.read(spreadsheet=SPREADSHEET, worksheet="Watchlists", ttl="5m")
    
    if not raw_watchlist_df.empty:
        watchlist_df = pd.DataFrame(raw_watchlist_df.values.tolist(), columns=raw_watchlist_df.columns)
    else:
        watchlist_df = raw_watchlist_df

    # ==========================================
    # UPGRADED DYNAMIC CONFIGURATOR
    # ==========================================
    with st.expander("⚙️ Add New Stock to Watchlist", expanded=True):
        st.caption("Select an existing list or create a new one. The entry price will be fetched automatically based on the date you select.")
        
        existing_lists = []
        if 'List Name' in watchlist_df.columns:
            existing_lists = [str(name).strip() for name in watchlist_df['List Name'].unique() if pd.notnull(name) and str(name).strip() != '']
        
        list_options = ["➕ Create New List..."] + existing_lists
        
        col1, col2, col3 = st.columns(3)
        
        # 1. Dynamic List Name
        selected_list = col1.selectbox("Watchlist Category", options=list_options)
        if selected_list == "➕ Create New List...":
            final_list_name = col1.text_input("Enter New List Name", placeholder="e.g. Pharma, Defence")
        else:
            final_list_name = selected_list
            
        # 2. Hybrid Ticker Selection (Type-ahead vs Manual)
        manual_override = col2.toggle("Enter micro-cap manually")
        
        if manual_override:
            new_ticker = col2.text_input("Manual Ticker Entry", placeholder="e.g. NEWIPO.NS")
        else:
            new_ticker = col2.selectbox("Search Ticker", options=sorted(POPULAR_STOCKS))
            
        # 3. Date Selection
        new_date = col3.date_input("Hypothetical Entry Date")
        
        if st.button("➕ Auto-Fetch Price & Save", type="primary"):
            if final_list_name and new_ticker:
                ticker_symbol = new_ticker.strip().upper()
                if not ticker_symbol.endswith('.NS') and not ticker_symbol.endswith('.BO'):
                    ticker_symbol += '.NS' 
                
                with st.spinner(f"Fetching historical price for {ticker_symbol} around {new_date}..."):
                    try:
                        import yfinance as yf
                        stock = yf.Ticker(ticker_symbol)
                        end_date = new_date + pd.Timedelta(days=7)
                        hist = stock.history(start=new_date.strftime("%Y-%m-%d"), end=end_date.strftime("%Y-%m-%d"))
                        
                        if not hist.empty:
                            fetched_price = float(hist['Close'].iloc[0])
                            actual_traded_date = hist.index[0].strftime("%Y-%m-%d")
                            
                            # Clean the ticker for display (remove .NS if you want, or keep it. We'll strip it for the sheet)
                            display_ticker = new_ticker.replace('.NS', '').replace('.BO', '').upper()
                            
                            ws_watchlists.append_row([
                                final_list_name.strip(), 
                                display_ticker, 
                                actual_traded_date, 
                                fetched_price
                            ])
                            st.success(f"Successfully added {display_ticker}! Entry price logged at ₹{fetched_price:.2f} (from {actual_traded_date}).")
                            st.cache_data.clear()
                            st.rerun()
                        else:
                            st.error(f"Could not find any trading data for {ticker_symbol} near that date. Please check the ticker symbol.")
                    except Exception as e:
                        st.error(f"Error fetching price: {e}")
            else:
                st.error("Please provide both a List Name and a Stock Ticker.")

    if not watchlist_df.empty and len(watchlist_df) > 0:
        analyze_and_render_watchlists(watchlist_df)
    else:
        st.info("Your watchlist is empty. Use the form above to add your first stock!")
        
except Exception as e:
    st.error(f"A critical error occurred while connecting to Google Sheets: {e}")
