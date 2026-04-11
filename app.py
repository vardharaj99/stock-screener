import streamlit as st
from googleapiclient.discovery import build
from modules.google_auth import authenticate_user, get_user_spreadsheet_id
import warnings

warnings.filterwarnings('ignore')

# 1. PAGE CONFIG
st.set_page_config(
    page_title="StockScreener | Home", 
    page_icon="📈", 
    layout="wide"
)

# ==========================================
# 2. THE SECURE GATEKEEPER
# ==========================================
# This ensures no one sees the home page without logging in first.
# It also initializes the session so the 'ss_id' is ready for other pages.
try:
    creds = authenticate_user()
    ss_id = get_user_spreadsheet_id(creds)
    # We build the service once to verify connection is active
    service = build('sheets', 'v4', credentials=creds)
except Exception as e:
    st.error(f"Authentication setup failed: {e}")
    st.stop()

# ==========================================
# 3. HOME PAGE UI
# ==========================================
st.title("🚀 StockScreener Dashboard")

# Display a nice success message with user context
st.success(f"**Authenticated successfully!** Your data is stored in your private Google Drive.")

st.markdown(f"""
Welcome to your personal trading cockpit. This app uses your private Google account to manage 
watchlists and portfolios securely. 
---
""")

# Layout for Navigation
col1, col2, col3 = st.columns(3)

with col1:
    with st.container(border=True):
        st.subheader("👀 Watchlists")
        st.write("Track hypothetical entries and monitor stage analysis for NSE/BSE stocks.")
        if st.button("Open Watchlists", type="primary", use_container_width=True):
            st.switch_page("pages/1_👀_Watchlists.py")

with col2:
    with st.container(border=True):
        st.subheader("💼 Portfolio")
        st.write("Manage your actual holdings, track realized P&L, and plan tax-efficient exits.")
        # We will build this page next!
        st.button("Open Portfolio (Coming Soon)", disabled=True, use_container_width=True)

with col3:
    with st.container(border=True):
        st.subheader("⚙️ Database Info")
        st.write(f"**Connected File:** `StockScreener_DB`")
        st.write(f"**ID:** `{ss_id[:20]}...` ")
        st.caption("You can find this file in your Google Drive root folder.")

st.divider()

# Footer / Instructions
with st.expander("ℹ️ How it works"):
    st.write("""
    1. **Privacy:** The app only has permission to see files it creates (`StockScreener_DB`).
    2. **Data:** Your stock list is saved in a Google Sheet. You can open that sheet manually anytime in your Drive.
    3. **Sync:** If you add a stock on the Watchlist page, it updates your Google Sheet in real-time.
    """)

st.caption("v4.0 | Multi-Tenant Architecture | Private Google Auth Enabled")
