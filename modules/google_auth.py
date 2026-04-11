import streamlit as st
from requests_oauthlib import OAuth2Session
from googleapiclient.discovery import build
import google.oauth2.credentials

# Scopes and Constants
SCOPES = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive.file']
AUTH_URL = "https://accounts.google.com/o/oauth2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"

def authenticate_user():
    if "credentials" in st.session_state:
        return st.session_state.credentials

    client_id = st.secrets["auth"]["client_id"]
    client_secret = st.secrets["auth"]["client_secret"]
    redirect_uri = st.secrets["auth"]["redirect_uri"]

    # 1. Initialize the OAuth2 Session
    google = OAuth2Session(client_id, scope=SCOPES, redirect_uri=redirect_uri)

    # 2. Handle the Callback
    if "code" in st.query_params:
        try:
            # Manually exchange the code for a token
            token = google.fetch_token(
                TOKEN_URL,
                client_secret=client_secret,
                code=st.query_params["code"]
            )
            
            # Convert the raw token into Google Credentials object
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
            st.error(f"OAuth Exchange Error: {e}")
            st.stop()

    # 3. Show Login Button
    authorization_url, state = google.authorization_url(AUTH_URL, access_type="offline", prompt="consent")
    
    st.markdown("### 🔐 StockScreener Private")
    st.info("Log in to access your personal database in Google Drive.")
    st.link_button("🚀 Sign in with Google", authorization_url, type="primary")
    st.stop()

def get_user_spreadsheet_id(creds):
    drive = build('drive', 'v3', credentials=creds)
    sheets = build('sheets', 'v4', credentials=creds)
    
    query = "name = 'StockScreener_DB' and mimeType = 'application/vnd.google-apps.spreadsheet' and trashed = false"
    files = drive.files().list(q=query, spaces='drive', fields='files(id, name)').execute().get('files', [])
    
    if files:
        return files[0]['id']
    
    # Creation logic
    ss = sheets.spreadsheets().create(body={'properties': {'title': 'StockScreener_DB'}}, fields='spreadsheetId').execute()
    ss_id = ss.get('spreadsheetId')
    
    header = [["List Name", "Instrument", "Date Added", "Price Added"]]
    sheets.spreadsheets().values().update(
        spreadsheetId=ss_id, range="Sheet1!A1",
        valueInputOption="RAW", body={'values': header}).execute()
    
    req = {'requests': [{'updateSheetProperties': {'properties': {'sheetId': 0, 'title': 'Watchlists'}, 'fields': 'title'}}]}
    sheets.spreadsheets().batchUpdate(spreadsheetId=ss_id, body=req).execute()
    
    return ss_id
