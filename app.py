import streamlit as st
from streamlit_gsheets import GSheetsConnection

st.title("🔌 Security Validation Test")

# PASTE YOUR SPREADSHEET ID HERE
SPREADSHEET_ID = "18ci-lXIJAhb-T96DZ1bL5sEKVmishPTBItIMaACBRJw"

try:
    # 1. Wake up the robot using the Secrets you saved
    conn = st.connection("gsheets", type=GSheetsConnection)
    
    # 2. Ask the robot to read just the first 5 rows of your private sheet
    test_data = conn.read(spreadsheet=SPREADSHEET_ID, nrows=5)
    
    # 3. If it succeeds, show a green success message and the data!
    st.success("✅ Connection Successful! The robot has the right keys and can see the sheet.")
    st.dataframe(test_data)
    
except Exception as e:
    # If it fails, show a red error message and exactly what went wrong
    st.error("❌ Connection Failed. Double-check your Streamlit Secrets formatting.")
    st.write("Error details for debugging:")
    st.write(e)
