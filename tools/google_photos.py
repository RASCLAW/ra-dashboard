"""
Google Photos API tool -- list, search, and download photos.

Usage:
    python tools/photos/google_photos.py --list [--limit 20]
    python tools/photos/google_photos.py --search "beach"
    python tools/photos/google_photos.py --albums
    python tools/photos/google_photos.py --download MEDIA_ITEM_ID --output /tmp/photo.jpg
"""

import argparse
import json
import os
import sys
from pathlib import Path

import requests
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

PROJECT_DIR = Path(__file__).parent.parent.parent
TOKEN_FILE = PROJECT_DIR / "token_photos.json"
CREDS_FILE = PROJECT_DIR / "credentials.json"

SCOPES = ["https://www.googleapis.com/auth/photoslibrary.readonly"]
BASE = "https://photoslibrary.googleapis.com/v1"


def get_credentials():
    """Get or refresh Google Photos OAuth credentials."""
    creds = None
    if TOKEN_FILE.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not CREDS_FILE.exists():
                print(f"Error: {CREDS_FILE} not found", file=sys.stderr)
                sys.exit(1)
            flow = InstalledAppFlow.from_client_secrets_file(str(CREDS_FILE), SCOPES)
            creds = flow.run_local_server(port=8091, open_browser=False)

        TOKEN_FILE.write_text(creds.to_json())
        print("Token saved.", file=sys.stderr)

    return creds


def api_get(creds, endpoint, params=None):
    headers = {"Authorization": f"Bearer {creds.token}"}
    resp = requests.get(f"{BASE}/{endpoint}", headers=headers, params=params)
    if not resp.ok:
        raise RuntimeError(f"API error {resp.status_code}: {resp.text}")
    return resp.json()


def api_post(creds, endpoint, body):
    headers = {
        "Authorization": f"Bearer {creds.token}",
        "Content-Type": "application/json",
    }
    resp = requests.post(f"{BASE}/{endpoint}", headers=headers, json=body)
    if not resp.ok:
        raise RuntimeError(f"API error {resp.status_code}: {resp.text}")
    return resp.json()


def list_media(creds, limit=20, page_token=None):
    """List recent media items."""
    params = {"pageSize": min(limit, 100)}
    if page_token:
        params["pageToken"] = page_token
    data = api_get(creds, "mediaItems", params)
    items = data.get("mediaItems", [])
    for item in items:
        ts = item.get("mediaMetadata", {}).get("creationTime", "")
        mime = item.get("mimeType", "")
        fname = item.get("filename", "")
        print(f"  {item['id'][:20]}... | {fname} | {mime} | {ts}")
    print(f"\nTotal shown: {len(items)}")
    if data.get("nextPageToken"):
        print(f"Next page token: {data['nextPageToken']}")
    return items


def search_media(creds, query=None, date_from=None, date_to=None, limit=20):
    """Search media items by filters."""
    body = {"pageSize": min(limit, 100)}
    filters = {}

    if date_from or date_to:
        date_filter = {"ranges": [{}]}
        if date_from:
            parts = date_from.split("-")
            date_filter["ranges"][0]["startDate"] = {
                "year": int(parts[0]), "month": int(parts[1]), "day": int(parts[2])
            }
        if date_to:
            parts = date_to.split("-")
            date_filter["ranges"][0]["endDate"] = {
                "year": int(parts[0]), "month": int(parts[1]), "day": int(parts[2])
            }
        filters["dateFilter"] = date_filter

    if filters:
        body["filters"] = filters

    data = api_post(creds, "mediaItems:search", body)
    items = data.get("mediaItems", [])
    for item in items:
        ts = item.get("mediaMetadata", {}).get("creationTime", "")
        fname = item.get("filename", "")
        print(f"  {item['id'][:20]}... | {fname} | {ts}")
    print(f"\nTotal shown: {len(items)}")
    return items


def list_albums(creds, limit=50):
    """List all albums."""
    data = api_get(creds, "albums", {"pageSize": min(limit, 50)})
    albums = data.get("albums", [])
    for album in albums:
        count = album.get("mediaItemsCount", 0)
        print(f"  {album['id'][:20]}... | {album['title']} | {count} items")
    print(f"\nTotal albums: {len(albums)}")
    return albums


def download_media(creds, media_id, output_path):
    """Download a media item to a local file."""
    data = api_get(creds, f"mediaItems/{media_id}")
    base_url = data.get("baseUrl", "")
    mime = data.get("mimeType", "")

    if "image" in mime:
        url = f"{base_url}=d"
    elif "video" in mime:
        url = f"{base_url}=dv"
    else:
        url = base_url

    resp = requests.get(url, stream=True)
    if not resp.ok:
        raise RuntimeError(f"Download failed: {resp.status_code}")

    with open(output_path, "wb") as f:
        for chunk in resp.iter_content(chunk_size=8192):
            f.write(chunk)

    size = os.path.getsize(output_path)
    print(f"Downloaded: {output_path} ({size:,} bytes)")
    return output_path


def main():
    parser = argparse.ArgumentParser(description="Google Photos API tool")
    parser.add_argument("--list", action="store_true", help="List recent photos")
    parser.add_argument("--search", type=str, help="Search photos")
    parser.add_argument("--albums", action="store_true", help="List albums")
    parser.add_argument("--download", type=str, help="Download a media item by ID")
    parser.add_argument("--output", type=str, default="/tmp/photo.jpg", help="Output path for download")
    parser.add_argument("--limit", type=int, default=20, help="Number of results")
    parser.add_argument("--date-from", type=str, help="Filter from date (YYYY-MM-DD)")
    parser.add_argument("--date-to", type=str, help="Filter to date (YYYY-MM-DD)")
    args = parser.parse_args()

    creds = get_credentials()

    if args.list:
        list_media(creds, limit=args.limit)
    elif args.search is not None:
        search_media(creds, query=args.search, date_from=args.date_from, date_to=args.date_to, limit=args.limit)
    elif args.albums:
        list_albums(creds, limit=args.limit)
    elif args.download:
        download_media(creds, args.download, args.output)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
