"""
gmail_reader.py — Fetch unread emails from Gmail
READ ONLY MODE - Emails stay UNREAD
BRANCH: THANE NEW - Sales Only
UPDATED: Using THANENEW_ prefixed secrets for OAuth
"""

import base64
import hashlib
import logging
import os
import re
from datetime import datetime
from typing import Dict, List, Optional

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from config import GMAIL_QUERY, GMAIL_USER_ID, MAX_EMAILS_PER_RUN, GMAIL_SCOPES
from error_handler import EmailFetchError, with_retry
from utils import received_timestamp_to_datetime

logger = logging.getLogger(__name__)

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp"}
ATTACHMENTS_DIR = "attachments"


class GmailReader:
    def __init__(self):
        os.makedirs(ATTACHMENTS_DIR, exist_ok=True)
        self._service = None
        self._oauth_creds = None

    def _get_oauth_creds(self):
        if self._oauth_creds:
            return self._oauth_creds

        import os

        # UPDATED: Using THANENEW_ prefixed secrets
        refresh_token = os.environ.get("THANENEW_REFRESH_TOKEN", "")
        client_id = os.environ.get("THANENEW_CLIENT_ID", "")
        client_secret = os.environ.get("THANENEW_CLIENT_SECRET", "")

        if refresh_token and client_id and client_secret:
            self._oauth_creds = Credentials(
                token=None,
                refresh_token=refresh_token,
                token_uri="https://oauth2.googleapis.com/token",
                client_id=client_id,
                client_secret=client_secret,
                scopes=GMAIL_SCOPES,
            )
            logger.info("OAuth credentials loaded from environment (THANENEW)")
            return self._oauth_creds

        raise Exception("No OAuth credentials found for THANENEW branch")

    def _get_service(self):
        if self._service:
            return self._service
        creds = self._get_oauth_creds()
        self._service = build("gmail", "v1", credentials=creds)
        logger.info("Gmail service initialised (READ ONLY)")
        return self._service

    def _extract_email_address(self, from_header: str) -> str:
        match = re.search(r'<([^>]+)>', from_header)
        if match:
            return match.group(1).strip().lower()
        match = re.search(r'[\w.+-]+@[\w.-]+\.\w+', from_header)
        if match:
            return match.group(0).strip().lower()
        return from_header.strip().lower()

    @with_retry()
    def fetch_emails(self) -> List[Dict]:
        svc = self._get_service()
        emails = []

        try:
            result = svc.users().messages().list(
                userId=GMAIL_USER_ID,
                q=GMAIL_QUERY,
                maxResults=MAX_EMAILS_PER_RUN,
            ).execute()
        except HttpError as exc:
            raise EmailFetchError(
                "Gmail list() failed",
                "api_error",
                {"status": exc.resp.status, "reason": exc.reason},
            ) from exc

        messages = result.get("messages", [])
        logger.info(f"Found {len(messages)} unread email(s) from allowed senders")
        print(f"DEBUG: Gmail API returned {len(messages)} messages", flush=True)

        for msg_stub in messages:
            try:
                msg = svc.users().messages().get(
                    userId=GMAIL_USER_ID, id=msg_stub["id"], format="full"
                ).execute()

                subject = ""
                from_email = ""
                for h in msg["payload"].get("headers", []):
                    if h["name"].lower() == "subject":
                        subject = h["value"]
                    elif h["name"].lower() == "from":
                        from_email = h["value"]

                sender_email = self._extract_email_address(from_email)
                print(f"DEBUG: Processing email from: {sender_email}", flush=True)

                body_parts = []
                att_paths = []
                self._walk_parts(svc, msg_stub["id"], msg["payload"], body_parts, att_paths)
                body = "\n".join(body_parts)

                received_ms = int(msg.get("internalDate", 0))
                received_at = received_timestamp_to_datetime(received_ms) if received_ms else datetime.now()

                emails.append({
                    "id": msg_stub["id"],
                    "subject": subject,
                    "from": from_email,
                    "sender_email": sender_email,
                    "body": body,
                    "attachments": att_paths,
                    "hash": hashlib.md5(f"{msg_stub['id']}|{subject}".encode()).hexdigest(),
                    "received_at": received_at,
                    "received_ms": received_ms,
                })

                logger.info(f"Successfully fetched email from: {sender_email}")

            except Exception as e:
                logger.error(f"Error processing message {msg_stub['id']}: {e}")
                continue

        logger.info(f"Fetched {len(emails)} email(s) total")
        return emails

    def _walk_parts(self, svc, msg_id, part, body_ref, att_ref):
        mime = part.get("mimeType", "")

        if mime == "text/plain":
            data = part.get("body", {}).get("data", "")
            if data:
                text = base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")
                body_ref.append(text)

        elif part.get("filename") and part.get("body", {}).get("attachmentId"):
            ext = os.path.splitext(part["filename"])[1].lower()
            if ext in IMAGE_EXTENSIONS:
                path = self._download_attachment(svc, msg_id, part)
                if path:
                    att_ref.append(path)

        for sub in part.get("parts", []):
            self._walk_parts(svc, msg_id, sub, body_ref, att_ref)

    def _download_attachment(self, svc, msg_id, part):
        try:
            att = svc.users().messages().attachments().get(
                userId=GMAIL_USER_ID,
                messageId=msg_id,
                id=part["body"]["attachmentId"]
            ).execute()

            raw = base64.urlsafe_b64decode(att["data"])
            filename = part["filename"]
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            safe_name = f"{timestamp}_{filename}"
            path = os.path.join(ATTACHMENTS_DIR, safe_name)

            with open(path, "wb") as fh:
                fh.write(raw)

            logger.info(f"Downloaded attachment: {safe_name}")
            return path

        except Exception as exc:
            logger.error(f"Attachment download failed: {exc}")
            return None
