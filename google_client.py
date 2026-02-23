import json
import streamlit as st
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from google.auth.transport.requests import Request

SCOPES = [
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/documents",
]

def get_credentials():
    raw = st.secrets["google_oauth"]["authorized_user_json"]
    info = json.loads(raw)

    creds = Credentials.from_authorized_user_info(info, scopes=SCOPES)

    if creds.expired and creds.refresh_token:
        creds.refresh(Request())

    return creds


def get_drive_service():
    return build("drive", "v3", credentials=get_credentials())


def get_docs_service():
    return build("docs", "v1", credentials=get_credentials())