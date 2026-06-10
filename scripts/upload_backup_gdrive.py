#!/usr/bin/env python3
"""Upload a DB backup to Google Drive and prune old copies.

Uses the same service account as the Google Sheets sync. Backups are stored
in a folder owned by the service account and shared read-only with SHARE_WITH,
so they survive a total loss of the server.

Usage: upload_backup_gdrive.py <file> [--keep-days N]
"""
import argparse
import datetime as dt
import os
import sys

from google.oauth2 import service_account
from google.auth.transport.requests import AuthorizedSession

API = "https://www.googleapis.com/drive/v3"
UPLOAD_API = "https://upload.googleapis.com/upload/drive/v3"

DEFAULT_CREDENTIALS = os.environ.get(
    "GOOGLE_SHEETS_CREDENTIALS",
    "/opt/alex12060-bot/google_sheets_credentials.json",
)
FOLDER_NAME = "alex12060-db-backups"
SHARE_WITH = "gamemolchanov@gmail.com"


def get_session(credentials_path):
    creds = service_account.Credentials.from_service_account_file(
        credentials_path, scopes=["https://www.googleapis.com/auth/drive.file"]
    )
    return AuthorizedSession(creds)


def find_or_create_folder(session, name):
    query = (
        f"name = '{name}' and mimeType = 'application/vnd.google-apps.folder' "
        "and trashed = false"
    )
    r = session.get(f"{API}/files", params={"q": query, "fields": "files(id)"})
    r.raise_for_status()
    files = r.json().get("files", [])
    if files:
        return files[0]["id"]
    r = session.post(
        f"{API}/files",
        json={"name": name, "mimeType": "application/vnd.google-apps.folder"},
    )
    r.raise_for_status()
    print(f"Created Drive folder '{name}'")
    return r.json()["id"]


def ensure_shared(session, folder_id, email):
    r = session.get(
        f"{API}/files/{folder_id}/permissions",
        params={"fields": "permissions(emailAddress)"},
    )
    r.raise_for_status()
    for perm in r.json().get("permissions", []):
        if (perm.get("emailAddress") or "").lower() == email.lower():
            return
    r = session.post(
        f"{API}/files/{folder_id}/permissions",
        params={"sendNotificationEmail": "false"},
        json={"type": "user", "role": "reader", "emailAddress": email},
    )
    r.raise_for_status()
    print(f"Shared backup folder with {email}")


def upload(session, folder_id, path):
    metadata = {"name": os.path.basename(path), "parents": [folder_id]}
    r = session.post(
        f"{UPLOAD_API}/files",
        params={"uploadType": "resumable"},
        headers={"X-Upload-Content-Type": "application/gzip"},
        json=metadata,
    )
    r.raise_for_status()
    location = r.headers["Location"]
    with open(path, "rb") as f:
        r = session.put(
            location, data=f.read(), headers={"Content-Type": "application/gzip"}
        )
    r.raise_for_status()
    return r.json()["id"]


def prune(session, folder_id, keep_days):
    cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=keep_days)
    query = (
        f"'{folder_id}' in parents and trashed = false "
        f"and createdTime < '{cutoff.strftime('%Y-%m-%dT%H:%M:%S')}'"
    )
    r = session.get(f"{API}/files", params={"q": query, "fields": "files(id,name)"})
    r.raise_for_status()
    for f in r.json().get("files", []):
        session.delete(f"{API}/files/{f['id']}").raise_for_status()
        print(f"Pruned old Drive backup: {f['name']}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("file", help="path to the backup file")
    parser.add_argument("--keep-days", type=int, default=30)
    parser.add_argument("--credentials", default=DEFAULT_CREDENTIALS)
    args = parser.parse_args()

    if not os.path.isfile(args.file):
        sys.exit(f"No such file: {args.file}")

    session = get_session(args.credentials)
    folder_id = find_or_create_folder(session, FOLDER_NAME)
    ensure_shared(session, folder_id, SHARE_WITH)
    file_id = upload(session, folder_id, args.file)
    print(f"Uploaded {os.path.basename(args.file)} to Drive (id={file_id})")
    prune(session, folder_id, args.keep_days)


if __name__ == "__main__":
    main()
