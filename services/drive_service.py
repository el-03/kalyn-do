# services/drive_service.py
from typing import Optional, List, Dict
from googleapiclient.discovery import Resource
from googleapiclient.http import MediaIoBaseUpload
from googleapiclient.errors import HttpError


def find_file_in_folder_by_name(
    drive: Resource,
    folder_id: str,
    filename: str,
) -> Optional[Dict]:
    query = (
        f"name = '{filename}' and "
        f"'{folder_id}' in parents and "
        f"trashed = false"
    )

    resp = drive.files().list(
        q=query,
        fields="files(id, name, mimeType)",
        pageSize=1,
    ).execute()

    files: List[Dict] = resp.get("files", [])
    return files[0] if files else None


def upload_file_to_folder(
    drive: Resource,
    folder_id: str,
    filename: str,
    mimetype: str,
    media_stream,
) -> str:
    media = MediaIoBaseUpload(
        media_stream,
        mimetype=mimetype,
        resumable=False,
    )

    metadata = {
        "name": filename,
        "parents": [folder_id],
    }

    file = drive.files().create(
        body=metadata,
        media_body=media,
        fields="id",
    ).execute()

    return file["id"]


def ensure_file_public_and_get_url(drive: Resource, file_id: str) -> str:
    """
    Make the file readable by anyone with the link and return a direct download URL.
    This gives Docs a URL it can actually fetch.
    """
    # Make file public (if not already)
    drive.permissions().create(
        fileId=file_id,
        body={"type": "anyone", "role": "reader"},
        fields="id",
    ).execute()

    # Build a direct download URL that Docs can fetch
    return f"https://drive.google.com/uc?id={file_id}&export=download"