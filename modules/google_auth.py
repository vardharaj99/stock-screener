import streamlit as st
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build

SCOPES = [
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive.file'
]

def authenticate_user():
    # 1. Return existing credentials if already logged in
    if "credentials" in st.session_state:
        return st.session_state.credentials

    # 2. Configure the Flow
    client_config = {
        "web": {
            "client_id": st.secrets["auth"]["client_id"],
            "client_secret": st.secrets["auth"]["client_secret"],
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
        }
    }

    flow = Flow.from_client_config(
        client_config,
        scopes=SCOPES,
        redirect_uri=st.secrets["auth"]["redirect_uri"]
    )

    # 3. Handle the callback from Google
    # We use st.query_params to detect if Google sent us back a 'code'
    params = st.query_params
    if "code" in params:
        try:
            # THE FIX: We explicitly pass code_verifier=None
            # This tells the library NOT to look for a verifier, 
            # relying solely on our Client Secret for security.
            flow.fetch_token(code=params["code"], code_verifier=None)
            
            st.session_state.credentials = flow.credentials
            st.query_params.clear()
            st.rerun()
        except Exception as e:
            st.error(f"Failed to exchange code for token: {e}")
            st.stop()

    # 4. Generate the Auth URL if no code is present
    # We must ensure the URL generation also doesn't expect a verifier
    auth_url, _ = flow.authorization_url(
        prompt='consent',
        access_type='offline'
    )
    
    # UI Presentation
    st.markdown("### 🔐 StockScreener Private")
    st.info("Log in to access your personal database in Google Drive.")
    st.link_button("🚀 Sign in with Google", auth_url, type="primary")
    st.stop()

def get_user_spreadsheet_id(creds):
    """Finds or creates the StockScreener_DB file."""
    drive = build('drive', 'v3', credentials=creds)
    sheets = build('sheets', 'v4', credentials=creds)
    
    query = "name = 'StockScreener_DB' and mimeType = 'application/vnd.google-apps.spreadsheet' and trashed = false"
    files = drive.files().list(q=query, spaces='drive', fields='files(id, name)').execute().get('files', [])
    
    if files:
        return files[0]['id']
    
    # Create the database if missing
    ss = sheets.spreadsheets().create(
        body={'properties': {'title': 'StockScreener_DB'}}, 
        fields='spreadsheetId'
    ).execute()
    ss_id = ss.get('spreadsheetId')
    
    # Initialize headers
    header = [["List Name", "Instrument", "Date Added", "Price Added"]]
    sheets.spreadsheets().values().update(
        spreadsheetId=ss_id, range="Sheet1!A1",
        valueInputOption="RAW", body={'values': header}).execute()
    
    # Name the sheet correctly
    req = {'requests': [{'updateSheetProperties': {'properties': {'sheetId': 0, 'title': 'Watchlists'}, 'fields': 'title'}}]}
    sheets.spreadsheets().batchUpdate(spreadsheetId=ss_id, body={'requests': req}).execute()
    
    return ss_id
