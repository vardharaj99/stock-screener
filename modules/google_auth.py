import streamlit as st
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build

SCOPES = [
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive.file'
]

def authenticate_user():
    flow = Flow.from_client_config(
        {"web": {
            "client_id": "1013542865801-9tl0rre04b2sf7k69jc74d62vkajhehl.apps.googleusercontent.com",
            "client_secret": st.secrets["auth"]["client_secret"],
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
        }},
        scopes=SCOPES,
        redirect_uri=st.secrets["auth"]["redirect_uri"]
    )

    # Handle the OAuth callback
    if "code" in st.query_params and "credentials" not in st.session_state:
        flow.fetch_token(code=st.query_params["code"])
        st.session_state.credentials = flow.credentials
        st.query_params.clear()
        st.rerun()

    if "credentials" not in st.session_state:
        auth_url, _ = flow.authorization_url(prompt='consent', access_type='offline')
        st.markdown("### 🔐 StockScreener Private")
        st.info("Log in to access your personal secure database in Google Drive.")
        st.link_button("🚀 Sign in with Google", auth_url, type="primary")
        st.stop()

    return st.session_state.credentials

def get_user_spreadsheet_id(creds):
    drive = build('drive', 'v3', credentials=creds)
    sheets = build('sheets', 'v4', credentials=creds)
    
    query = "name = 'StockScreener_DB' and mimeType = 'application/vnd.google-apps.spreadsheet' and trashed = false"
    files = drive.files().list(q=query, spaces='drive').execute().get('files', [])
    
    if files:
        return files[0]['id']
    
    # Creation logic
    st.toast("Creating your private StockScreener_DB...")
    ss = sheets.spreadsheets().create(body={'properties': {'title': 'StockScreener_DB'}}, fields='spreadsheetId').execute()
    ss_id = ss.get('spreadsheetId')
    
    # Headers
    header = [["List Name", "Instrument", "Date Added", "Price Added"]]
    sheets.spreadsheets().values().update(
        spreadsheetId=ss_id, range="Sheet1!A1",
        valueInputOption="RAW", body={'values': header}).execute()
    
    # Rename to Watchlists
    req = {'requests': [{'updateSheetProperties': {'properties': {'sheetId': 0, 'title': 'Watchlists'}, 'fields': 'title'}}]}
    sheets.spreadsheets().batchUpdate(spreadsheetId=ss_id, body=req).execute()
    
    return ss_id
