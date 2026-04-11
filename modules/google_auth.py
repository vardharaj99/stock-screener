import streamlit as st
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
import pandas as pd

# The scopes required to manage the specific spreadsheet
SCOPES = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive.file']

def get_google_auth_flow():
    return Flow.from_client_config(
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

def authenticate_user():
    if "google_auth_code" not in st.session_state:
        flow = get_google_auth_flow()
        auth_url, _ = flow.authorization_url(prompt='consent')
        st.link_button("🔑 Sign in with Google", auth_url)
        st.stop()
    
    # Process the callback
    if "credentials" not in st.session_state:
        flow = get_google_auth_flow()
        flow.fetch_token(code=st.session_state.google_auth_code)
        st.session_state.credentials = flow.credentials

def get_user_database():
    creds = st.session_state.credentials
    drive_service = build('drive', 'v3', credentials=creds)
    sheets_service = build('sheets', 'v4', credentials=creds)
    
    # 1. Search for existing DB
    query = "name = 'StockScreener_DB' and mimeType = 'application/vnd.google-apps.spreadsheet'"
    results = drive_service.files().list(q=query, spaces='drive', fields='files(id, name)').execute()
    files = results.get('files', [])
    
    if files:
        return files[0]['id']
    
    # 2. Create if not exists
    spreadsheet = {
        'properties': {'title': 'StockScreener_DB'}
    }
    ss = sheets_service.spreadsheets().create(body=spreadsheet, fields='spreadsheetId').execute()
    ss_id = ss.get('spreadsheetId')
    
    # 3. Setup Initial Structure (Watchlists)
    body = {'values': [["List Name", "Instrument", "Date Added", "Price Added"]]}
    sheets_service.spreadsheets().values().update(
        spreadsheetId=ss_id, range="Sheet1!A1",
        valueInputOption="RAW", body=body).execute()
    
    # Rename Sheet1 to Watchlists
    requests = [{'updateSheetProperties': {'properties': {'sheetId': 0, 'title': 'Watchlists'}, 'fields': 'title'}}]
    sheets_service.spreadsheets().batchUpdate(spreadsheetId=ss_id, body={'requests': requests}).execute()
    
    return ss_id
