import streamlit as st
from streamlit_gsheets import GSheetsConnection

st.title("🔌 Security Validation Test (Cache Buster)")

# Your verified exact ID
SPREADSHEET_ID = "18ci-lXIJAhb-T96DZ1bL5sEKVmishPTBItIMaACBRJw"

try:
    conn = st.connection("gsheets", type=GSheetsConnection)
    
    # MAGIC FIX: Adding ttl=0 forces Streamlit to ignore its memory and check live!
    test_data = conn.read(spreadsheet=SPREADSHEET_ID, nrows=5, ttl=0)
    
    st.success("✅ Connection Successful! The cache is busted and the robot is in.")
    st.dataframe(test_data)
    
except Exception as e:
    st.error("❌ Connection Failed.")
    st.write("Error details for debugging:")
    st.write(e)
