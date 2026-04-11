import streamlit as st
from requests_oauthlib import OAuth2Session
from googleapiclient.discovery import build
import google.oauth2.credentials
import os

# 1. FORCE RELAXED SCOPES (The "Shut Up" command)
os.environ['OAUTHLIB_RELAX_TOKEN_SCOPE'] = '1'
os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'

# 2. USE ONE BROAD SCOPE (Less confusion for Google)
# drive.file allows us to manage any file the app creates (including Sheets)
SCOPES = ['https://www.googleapis.com/auth/drive.file']
AUTH_URL = "https://accounts.google.com/o/oauth2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"

def authenticate_user():
    if "credentials" in st.session_state:
        return st.session_state.credentials

    client_id = st.secrets["auth"]["client_id"]
    client_secret = st.secrets["auth"]["client_secret"]
    redirect_uri = st.secrets["auth"]["redirect_uri"]

    # Initialize session
    google = OAuth2Session(client_id, scope=SCOPES, redirect_uri=redirect_uri)

    # Handle Callback
    if "code" in st.query_params:
        try:
            # Exchange code for token
            token = google.fetch_token(
                TOKEN_URL,
                client_secret=client_secret,
                code=st.query_params["code"]
            )
            
            # Map to Google Credentials
            creds = google.oauth2.credentials.Credentials(
                token=token['access_token'],
                refresh_token=token.get('refresh_token'),
                token_uri=TOKEN_URL,
                client_id=client_id,
                client_secret=client_secret,
                scopes=SCOPES
            )
            
            st.session_state.credentials = creds
            st.query_params.clear()
            st.rerun()
        except Exception as e:
            # If it still fails, we force clear params so you're not stuck
            st.query_params.clear()
            st.error(f"Login failed: {e}")
            st.stop()

    # Login UI
    authorization_url, _ = google.authorization_url(
        AUTH_URL, 
        access_type="offline", 
        prompt="select_account consent"
    )
    
    st.markdown("### 🔐 StockScreener: Private Secure Login")
    st.info("Your data is stored in your own Google Drive. No one else has access.")
    st.link_button("🚀 Sign in with Google", authorization_url, type="primary")
    st.stop()

def get_user_spreadsheet_id(creds):
    # This remains unchanged - it works once we have the token!
    drive = build('drive', 'v3', credentials=creds)
    sheets = build('sheets', 'v4', credentials=creds)
    
    query = "name = 'StockScreener_DB' and mimeType = 'application/vnd.google-apps.spreadsheet' and trashed = false"
    files = drive.files().list(q=query, spaces='drive').execute().get('files', [])
    
    if files:
        return files[0]['id']
    
    # Create DB
    ss = sheets.spreadsheets().create(body={'properties': {'title': 'StockScreener_DB'}}, fields='spreadsheetId').execute()
    ss_id = ss.get('spreadsheetId')
    
    header = [["List Name", "Instrument", "Date Added", "Price Added"]]
    sheets.spreadsheets().values().update(spreadsheetId=ss_id, range="Sheet1!A1", valueInputOption="RAW", body={'values': header}).execute()
    
    req = {'requests': [{'updateSheetProperties': {'properties': {'sheetId': 0, 'title': 'Watchlists'}, 'fields': 'title'}}]}
    sheets.spreadsheets().batchUpdate(spreadsheetId=ss_id, body=req).execute()
    
    return ss_id
