import streamlit as st
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
import os

# Standard Google Scopes
SCOPES = [
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive.file'
]

def authenticate_user():
    # 1. If already authenticated, just return credentials
    if "credentials" in st.session_state:
        return st.session_state.credentials

    # 2. Initialize Flow
    # We use a helper to ensure Client ID and Secret are pulled correctly
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

    # 3. Handle the Callback from Google
    if "code" in st.query_params:
        # Retrieve the verifier we saved before the user left for Google
        code_verifier = st.session_state.get("code_verifier")
        
        try:
            # Exchange the code for actual credentials
            flow.fetch_token(
                code=st.query_params["code"],
                code_verifier=code_verifier
            )
            st.session_state.credentials = flow.credentials
            
            # Clean up session state and URL
            if "code_verifier" in st.session_state:
                del st.session_state["code_verifier"]
            st.query_params.clear()
            st.rerun()
        except Exception as e:
            st.error(f"Failed to exchange code for token: {e}")
            # If it fails, clear everything so the user can try a fresh login
            st.query_params.clear()
            st.stop()

    # 4. If not logged in, generate the Login URL
    # We explicitly generate a code_verifier and save it in session_state
    auth_url, _ = flow.authorization_url(
        prompt='consent',
        access_type='offline',
        include_granted_scopes='true'
    )
    
    # Store the verifier that fetch_token will need when the user returns
    st.session_state["code_verifier"] = flow.code_verifier

    # UI for Login
    st.markdown("### 🔐 StockScreener Private")
    st.info("Log in to access your personal database in Google Drive.")
    st.link_button("🚀 Sign in with Google", auth_url, type="primary")
    st.stop()

def get_user_spreadsheet_id(creds):
    """Finds or creates the StockScreener_DB file."""
    drive = build('drive', 'v3', credentials=creds)
    sheets = build('sheets', 'v4', credentials=creds)
    
    query = "name = 'StockScreener_DB' and mimeType = 'application/vnd.google-apps.spreadsheet' and trashed = false"
    files = drive.files().list(q=query, spaces='drive').execute().get('files', [])
    
    if files:
        return files[0]['id']
    
    # Create the file if it doesn't exist
    ss = sheets.spreadsheets().create(
        body={'properties': {'title': 'StockScreener_DB'}}, 
        fields='spreadsheetId'
    ).execute()
    ss_id = ss.get('spreadsheetId')
    
    # Add Headers
    header = [["List Name", "Instrument", "Date Added", "Price Added"]]
    sheets.spreadsheets().values().update(
        spreadsheetId=ss_id, range="Sheet1!A1",
        valueInputOption="RAW", body={'values': header}).execute()
    
    # Rename default sheet to Watchlists
    req = {'requests': [{'updateSheetProperties': {'properties': {'sheetId': 0, 'title': 'Watchlists'}, 'fields': 'title'}}]}
    sheets.spreadsheets().batchUpdate(spreadsheetId=ss_id, body={'requests': req}).execute()
    
    return ss_id
