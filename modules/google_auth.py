import streamlit as st
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
import pandas as pd

# The scopes required to manage the specific spreadsheet and find files in Drive
SCOPES = [
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive.file'
]

CLIENT_ID = "1013542865801-9tl0rre04b2sf7k69jc74d62vkajhehl.apps.googleusercontent.com"

def authenticate_user():
    """
    Handles the OAuth2 flow. 
    1. Checks if the user is already authenticated.
    2. Handles the redirect 'code' from Google.
    3. Displays a login button if neither of the above are true.
    """
    
    # Initialize the OAuth Flow
    # We use st.secrets for the Client Secret to keep it hidden from GitHub
    flow = Flow.from_client_config(
        {
            "web": {
                "client_id": CLIENT_ID,
                "client_secret": st.secrets["auth"]["client_secret"],
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
            }
        },
        scopes=SCOPES,
        redirect_uri=st.secrets["auth"]["redirect_uri"]
    )

    # Step 1: Check if we are returning from the Google Auth redirect (URL contains ?code=...)
    query_params = st.query_params
    if "code" in query_params and "credentials" not in st.session_state:
        try:
            flow.fetch_token(code=query_params["code"])
            st.session_state.credentials = flow.credentials
            # Clean the URL to remove the sensitive code
            st.query_params.clear()
            st.rerun()
        except Exception as e:
            st.error(f"Authentication failed: {e}")
            st.stop()

    # Step 2: Check if user is already logged in (credentials in session state)
    if "credentials" not in st.session_state:
        # Generate the Google Login URL
        auth_url, _ = flow.authorization_url(prompt='consent', access_type='offline')
        
        # Display a clean landing page for unauthenticated users
        st.markdown("### 🔐 StockScreener: Private Access")
        st.info("To protect your privacy, this app creates a personal database in your own Google Drive. No one else can see your watchlists or portfolios.")
        
        st.link_button("🚀 Sign in with Google", auth_url, type="primary")
        st.stop() # Prevents the rest of the app from running until logged in

    return st.session_state.credentials

def get_user_spreadsheet_id(creds):
    """
    Intelligently locates 'StockScreener_DB' in the user's Drive.
    If it doesn't exist, it creates it and sets up the required 'Watchlists' sheet.
    """
    drive_service = build('drive', 'v3', credentials=creds)
    sheets_service = build('sheets', 'v4', credentials=creds)
    
    # Search for the file by name
    query = "name = 'StockScreener_DB' and mimeType = 'application/vnd.google-apps.spreadsheet' and trashed = false"
    try:
        results = drive_service.files().list(q=query, spaces='drive', fields='files(id, name)').execute()
        files = results.get('files', [])
        
        if files:
            # Database found!
            return files[0]['id']
        
        # If not found, create a new one
        st.toast("First time login: Setting up your private database...")
        spreadsheet_body = {'properties': {'title': 'StockScreener_DB'}}
        ss = sheets_service.spreadsheets().create(body=spreadsheet_body, fields='spreadsheetId').execute()
        ss_id = ss.get('spreadsheetId')
        
        # Initial Header Setup for 'Watchlists'
        header_values = [["List Name", "Instrument", "Date Added", "Price Added"]]
        sheets_service.spreadsheets().values().update(
            spreadsheetId=ss_id,
            range="Sheet1!A1",
            valueInputOption="RAW",
            body={'values': header_values}
        ).execute()
        
        # Rename 'Sheet1' to 'Watchlists' for consistency with our app logic
        rename_request = {
            'requests': [
                {
                    'updateSheetProperties': {
                        'properties': {'sheetId': 0, 'title': 'Watchlists'},
                        'fields': 'title'
                    }
                }
            ]
        }
        sheets_service.spreadsheets().batchUpdate(spreadsheetId=ss_id, body=rename_request).execute()
        
        return ss_id
    
    except Exception as e:
        st.error(f"Error accessing Google Drive/Sheets: {e}")
        st.stop()
