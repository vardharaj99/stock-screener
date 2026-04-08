import streamlit as st
from streamlit_gsheets import GSheetsConnection

st.title("🔌 Security Validation Test (Cache Buster)")

# MAGIC FIX: Streamlit-gsheets needs the FULL URL, not just the ID!
SPREADSHEET = "https://docs.google.com/spreadsheets/d/18ci-lXIJAhb-T96DZ1bL5sEKVmishPTBItIMaACBRJw/edit?gid=0#gid=0"

try:
    conn = st.connection("gsheets", type=GSheetsConnection)
    
    # Passing the full URL
    test_data = conn.read(spreadsheet=SPREADSHEET, nrows=5, ttl=0)
    
    st.success("✅ Connection Successful! The robot is in.")
    st.dataframe(test_data)
    
except Exception as e:
    st.error("❌ Connection Failed.")
    st.write("Error details for debugging:")
    st.write(e)
