import streamlit as st
from requests_oauthlib import OAuth2Session
from googleapiclient.discovery import build
import google.oauth2.credentials as google_creds
from google.auth.transport.requests import Request
import requests
import datetime
import os

# ── Only disable HTTPS enforcement in local dev, never in production ─────────
if os.getenv("LOCAL_DEV") == "true":
    os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'

os.environ['OAUTHLIB_RELAX_TOKEN_SCOPE'] = '1'

# ── Scopes ───────────────────────────────────────────────────────────────────
# openid / email / profile      → fetch user's email for safe display
# spreadsheets                  → full read/write on the sheet
# drive.metadata.readonly       → minimal scope to search Drive by filename
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
    Build a google.oauth2.credentials.Credentials object from a raw token dict.

    Two fixes vs the original:
    1. `google` was the OAuth2Session instance, not the module — we import
       google.oauth2.credentials explicitly and call it directly.
    2. Pass expiry= so that creds.expired works correctly and token refresh
       can fire when needed. Without this, creds.expired is always False.
    """
    expiry = None
    if token.get('expires_at'):
        expiry = datetime.datetime.utcfromtimestamp(token['expires_at'])

    return google_creds.Credentials(
        token=token['access_token'],
        refresh_token=token.get('refresh_token'),
        token_uri=TOKEN_URL,
        client_id=client_id,
        client_secret=client_secret,
        scopes=SCOPES,
        expiry=expiry,
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


def _has_required_scopes(creds) -> bool:
    """
    Return True if the stored credentials cover all currently required scopes.
    Used to detect when scopes have changed between deployments.
    """
    granted = set(creds.scopes or [])
    required = set(SCOPES)
    return required.issubset(granted)


def get_fresh_creds():
    """
    Always returns a valid, non-expired Credentials object.

    Execution order:
    1. No session              → run full OAuth login flow (blocks with st.stop)
    2. Scope mismatch          → wipe stale session, re-run login flow
    3. Token expired           → silently refresh using refresh_token
    4. Token valid             → return as-is
    """
    creds = st.session_state.get("credentials")

    # ── 1. No session at all ─────────────────────────────────────────────────
    if creds is None:
        return authenticate_user()

    # ── 2. Scope change guard ────────────────────────────────────────────────
    # This must live HERE (not inside authenticate_user) because get_fresh_creds
    # returns early when creds exist — authenticate_user is never reached.
    # If scopes changed since the user last authorised, wipe and re-auth.
    if not _has_required_scopes(creds):
        st.session_state.pop("credentials", None)
        st.session_state.pop("user_email", None)
        st.session_state.pop("user_name", None)
        st.warning("App permissions were updated. Please sign in again to continue.")
        return authenticate_user()

    # ── 3. Refresh expired token ─────────────────────────────────────────────
    if creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            st.session_state.credentials = creds
        except Exception:
            # Refresh failed (token revoked, network error, etc.) — force re-login
            st.session_state.pop("credentials", None)
            st.session_state.pop("user_email", None)
            st.session_state.pop("user_name", None)
            st.rerun()

    # ── 4. All good ──────────────────────────────────────────────────────────
    return creds


def authenticate_user():
    """
    Full OAuth2 login flow. Renders the login button and halts on first visit.
    On the callback (Google redirects back with ?code=...), exchanges the code
    for a token, stores credentials and user email in session_state, then reruns.
    """
    # Already authenticated — shouldn't normally reach here, but guard anyway
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

            creds = _build_creds_from_token(token, client_id, client_secret)
            st.session_state.credentials = creds

            # Store email for display — never expose the raw token in the UI
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
        prompt="select_account consent",  # always show consent to capture latest scopes
    )

    st.markdown("### 🔐 StockScreener: Private Secure Login")
    st.info("Your data is stored in your own Google Drive. No one else has access.")
    st.link_button("🚀 Sign in with Google", authorization_url, type="primary")
    st.stop()


def get_user_spreadsheet_id(creds):
    """
    Find (or create) the user's StockScreener_DB spreadsheet.
    drive.metadata.readonly is enough to search; spreadsheets covers create/write.
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

    # ── First-time setup: create spreadsheet ─────────────────────────────────
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

    # Rename default sheet to "Watchlists"
    req = {'requests': [{'updateSheetProperties': {
        'properties': {'sheetId': 0, 'title': 'Watchlists'},
        'fields': 'title',
    }}]}
    sheets.spreadsheets().batchUpdate(spreadsheetId=ss_id, body=req).execute()

    return ss_id
