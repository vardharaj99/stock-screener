import streamlit as st
from requests_oauthlib import OAuth2Session
from googleapiclient.discovery import build
import google.oauth2.credentials as google_creds
from google.auth.transport.requests import Request
import requests
import os

# ── Bug 5 fix: only disable HTTPS enforcement in local dev ──────────────────
if os.getenv("LOCAL_DEV") == "true":
    os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'

os.environ['OAUTHLIB_RELAX_TOKEN_SCOPE'] = '1'

# ── Bug 2 fix: correct scopes ───────────────────────────────────────────────
# - openid / email / profile  → lets us fetch user's email for display
# - spreadsheets              → full read/write on the sheet
# - drive.metadata.readonly   → minimal scope to search Drive by filename
SCOPES = [
    'openid',
    'email',
    'profile',
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive.metadata.readonly',
]

AUTH_URL  = "https://accounts.google.com/o/oauth2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"


def _build_creds_from_token(token: dict, client_id: str, client_secret: str):
    """
    Bug 1 fix: `google` in the original code referred to the OAuth2Session
    instance, NOT the google.oauth2.credentials module.  We now import the
    module explicitly at the top and call it directly.
    """
    return google_creds.Credentials(
        token=token['access_token'],
        refresh_token=token.get('refresh_token'),
        token_uri=TOKEN_URL,
        client_id=client_id,
        client_secret=client_secret,
        scopes=SCOPES,
    )


def _fetch_user_info(access_token: str) -> dict:
    """Retrieve the logged-in user's profile from Google."""
    try:
        resp = requests.get(
            "https://www.googleapis.com/oauth2/v3/userinfo",
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()
    except Exception:
        return {}


def get_fresh_creds():
    """
    Bug 4 fix: always return a valid, non-expired credential object.
    If the token has expired and a refresh_token is available, refresh it
    silently.  If the session is completely missing, trigger the login flow.
    """
    creds = st.session_state.get("credentials")

    if creds is None:
        # No session at all — run the full OAuth flow
        return authenticate_user()

    # Refresh if expired
    if creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            st.session_state.credentials = creds
        except Exception:
            # Refresh failed (token revoked, etc.) — force re-login
            st.session_state.pop("credentials", None)
            st.session_state.pop("user_email", None)
            st.rerun()

    return creds


def authenticate_user():
    """
    Full OAuth2 flow.  Returns a google.oauth2.credentials.Credentials object.
    On first call (no session), renders the login button and stops.
    On callback (code in query params), exchanges code for token, stores creds.
    """
    # Already authenticated in this session
    if "credentials" in st.session_state:
        return st.session_state.credentials

    client_id     = st.secrets["auth"]["client_id"]
    client_secret = st.secrets["auth"]["client_secret"]
    redirect_uri  = st.secrets["auth"]["redirect_uri"]

    google_session = OAuth2Session(
        client_id,
        scope=SCOPES,
        redirect_uri=redirect_uri,
    )

    # ── Handle the OAuth callback ────────────────────────────────────────────
    if "code" in st.query_params:
        try:
            token = google_session.fetch_token(
                TOKEN_URL,
                client_secret=client_secret,
                code=st.query_params["code"],
            )

            # Bug 1 fix: use the explicitly imported module, not the session obj
            creds = _build_creds_from_token(token, client_id, client_secret)
            st.session_state.credentials = creds

            # Bug 3 fix: store email for display, never expose the raw token
            user_info = _fetch_user_info(token['access_token'])
            st.session_state.user_email = user_info.get("email", "unknown user")
            st.session_state.user_name  = user_info.get("name",  "")

            st.query_params.clear()
            st.rerun()

        except Exception as e:
            st.query_params.clear()
            st.error(f"Login failed: {e}")
            st.stop()

    # ── Show login UI ────────────────────────────────────────────────────────
    authorization_url, _ = google_session.authorization_url(
        AUTH_URL,
        access_type="offline",
        prompt="select_account consent",
    )

    st.markdown("### 🔐 StockScreener: Private Secure Login")
    st.info("Your data is stored in your own Google Drive. No one else has access.")
    st.link_button("🚀 Sign in with Google", authorization_url, type="primary")
    st.stop()


def get_user_spreadsheet_id(creds):
    """
    Find (or create) the user's StockScreener_DB spreadsheet.
    Uses drive.metadata.readonly to search, spreadsheets to create/write.
    """
    drive  = build('drive',  'v3', credentials=creds)
    sheets = build('sheets', 'v4', credentials=creds)

    query = (
        "name = 'StockScreener_DB' "
        "and mimeType = 'application/vnd.google-apps.spreadsheet' "
        "and trashed = false"
    )
    files = drive.files().list(q=query, spaces='drive').execute().get('files', [])

    if files:
        return files[0]['id']

    # ── First-time setup: create the spreadsheet ─────────────────────────────
    ss = sheets.spreadsheets().create(
        body={'properties': {'title': 'StockScreener_DB'}},
        fields='spreadsheetId',
    ).execute()
    ss_id = ss['spreadsheetId']

    # Write header row
    header = [["List Name", "Instrument", "Date Added", "Price Added"]]
    sheets.spreadsheets().values().update(
        spreadsheetId=ss_id,
        range="Sheet1!A1",
        valueInputOption="RAW",
        body={'values': header},
    ).execute()

    # Rename the default sheet to "Watchlists"
    req = {'requests': [{'updateSheetProperties': {
        'properties': {'sheetId': 0, 'title': 'Watchlists'},
        'fields': 'title',
    }}]}
    sheets.spreadsheets().batchUpdate(spreadsheetId=ss_id, body=req).execute()

    return ss_id
