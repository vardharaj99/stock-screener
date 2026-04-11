import streamlit as st
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build

SCOPES = [
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive.file'
]

def authenticate_user():
    # 1. Check if we already have valid credentials in the session
    if "credentials" in st.session_state:
        return st.session_state.credentials

    # 2. Initialize the Flow
    flow = Flow.from_client_config(
        {
            "web": {
                "client_id": st.secrets["auth"]["client_id"],
                "client_secret": st.secrets["auth"]["client_secret"],
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
            }
        },
        scopes=SCOPES,
        redirect_uri=st.secrets["auth"]["redirect_uri"]
    )

    # 3. Handle the Redirect (when Google sends the user back with ?code=...)
    if "code" in st.query_params:
        try:
            # fetch_token exchanges the code for actual credentials
            flow.fetch_token(code=st.query_params["code"])
            st.session_state.credentials = flow.credentials
            # Clean the URL to prevent "code reuse" errors on refresh
            st.query_params.clear()
            st.rerun()
        except Exception as e:
            st.error(f"Failed to exchange code for token: {e}")
            st.stop()

    # 4. If no credentials, show login button
    auth_url, _ = flow.authorization_url(
        prompt='consent',
        access_type='offline',
        include_granted_scopes='true'
    )
    
    st.markdown("### 🔐 StockScreener Private")
    st.info("Sign in to access your personal database in Google Drive.")
    st.link_button("🚀 Sign in with Google", auth_url, type="primary")
    st.stop()

def get_user_spreadsheet_id(creds):
    # This part remains the same logic-wise, but we use the creds passed in
    drive = build('drive', 'v3', credentials=creds)
    sheets = build('sheets', 'v4', credentials=creds)
    
    query = "name = 'StockScreener_DB' and mimeType = 'application/vnd.google-apps.spreadsheet' and trashed = false"
    files = drive.files().list(q=query, spaces='drive').execute().get('files', [])
    
    if files:
        return files[0]['id']
    
    # Creation logic if missing
    ss = sheets.spreadsheets().create(body={'properties': {'title': 'StockScreener_DB'}}, fields='spreadsheetId').execute()
    ss_id = ss.get('spreadsheetId')
    
    # Headers Setup
    header = [["List Name", "Instrument", "Date Added", "Price Added"]]
    sheets.spreadsheets().values().update(
        spreadsheetId=ss_id, range="Sheet1!A1",
        valueInputOption="RAW", body={'values': header}).execute()
    
    # Rename default sheet
    req = {'requests': [{'updateSheetProperties': {'properties': {'sheetId': 0, 'title': 'Watchlists'}, 'fields': 'title'}}]}
    sheets.spreadsheets().batchUpdate(spreadsheetId=ss_id, body=req).execute()
    
    return ss_id
