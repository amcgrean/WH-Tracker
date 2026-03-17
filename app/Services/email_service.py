"""
email_service.py
----------------
Polls an IMAP inbox for emails whose subject contains "RMA #XXXXXXX"
(7-10 digits), extracts image attachments, saves them to disk, and
returns a list of dicts ready to be inserted as CreditImage records.

Supports any IMAP server.  Default is Office 365 (outlook.office365.com).

Environment variables expected (loaded from .env via python-dotenv):
    EMAIL_ADDRESS   - amcgrean@beisserlumber.com
    EMAIL_PASSWORD  - your password or M365 app password
    IMAP_SERVER     - defaults to outlook.office365.com
    IMAP_PORT       - defaults to 993
    IMAP_FOLDER     - mailbox folder to poll; defaults to INBOX.
                      For an Outlook subfolder named "Credits" use:
                      IMAP_FOLDER=Credits
                      For a nested folder (e.g. Inbox > Credits) use:
                      IMAP_FOLDER=INBOX/Credits
"""

import imaplib
import email
import os
import re
import logging
import requests
from datetime import datetime
from email.header import decode_header, make_header

# Microsoft Graph / HEIC support
import msal
from PIL import Image
import pillow_heif
pillow_heif.register_heif_opener()

logger = logging.getLogger(__name__)

# Allowed image/document extensions to save
ALLOWED_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.webp', '.pdf', '.tiff', '.tif', '.heic', '.heif'}

RMA_PATTERN = re.compile(r'RMA\s*#\s*(\d{7,10})', re.IGNORECASE)


def _decode_subject(raw_subject):
    """Safely decode an email subject that may be RFC2047-encoded."""
    try:
        return str(make_header(decode_header(raw_subject)))
    except Exception:
        return raw_subject or ''


def _sanitize_filename(filename):
    """Remove characters that are unsafe for filesystem paths."""
    filename = re.sub(r'[^\w\.\-]', '_', filename)
    return filename[:200]  # cap length


def _is_allowed_attachment(filename):
    ext = os.path.splitext(filename)[1].lower()
    return ext in ALLOWED_EXTENSIONS


def process_credit_emails(upload_base_dir, mark_as_read=True):
    """
    Connect to IMAP inbox, find unread emails with an RMA number in the
    subject, save attachments, and return a list of CreditImage field dicts.

    Parameters
    ----------
    upload_base_dir : str
        Absolute path to the root uploads folder (e.g. /path/to/project/uploads/credits).
        Subdirectories per RMA number will be created automatically.
    mark_as_read : bool
        Whether to mark processed emails as read so they are not reprocessed.

    Returns
    -------
    list[dict]
        Each dict maps directly to CreditImage columns:
        rma_number, filename, filepath, email_from, email_subject, received_at
    """
    email_address = os.environ.get('EMAIL_ADDRESS', '')
    email_password = os.environ.get('EMAIL_PASSWORD', '')
    imap_server   = os.environ.get('IMAP_SERVER', 'outlook.office365.com')
    imap_port     = int(os.environ.get('IMAP_PORT', 993))
    imap_folder   = os.environ.get('IMAP_FOLDER', 'INBOX')

    if not email_address or not email_password:
        raise ValueError(
            "EMAIL_ADDRESS and EMAIL_PASSWORD must be set in your .env file."
        )

    results = []

    try:
        conn = imaplib.IMAP4_SSL(imap_server, imap_port)
        conn.login(email_address, email_password)
        status, _ = conn.select(imap_folder)
        if status != 'OK':
            raise imaplib.IMAP4.error(f"Could not select folder '{imap_folder}' — check IMAP_FOLDER in .env")
        logger.info("Connected to %s as %s, folder: %s", imap_server, email_address, imap_folder)
    except imaplib.IMAP4.error as exc:
        logger.error("IMAP login failed: %s", exc)
        raise

    try:
        status, data = conn.search(None, 'UNSEEN')
        if status != 'OK':
            logger.warning("IMAP search returned status: %s", status)
            return results

        message_ids = data[0].split()
        logger.info("Found %d unread messages to check.", len(message_ids))

        for msg_id in message_ids:
            status, raw = conn.fetch(msg_id, '(RFC822)')
            if status != 'OK':
                continue

            msg = email.message_from_bytes(raw[0][1])

            subject = _decode_subject(msg.get('Subject', ''))
            rma_match = RMA_PATTERN.search(subject)

            if not rma_match:
                # Not an RMA email — leave unread and skip
                logger.debug("Skipping non-RMA email: %s", subject)
                continue

            rma_number = rma_match.group(1)
            sender     = msg.get('From', '')
            date_str   = msg.get('Date', '')

            # Parse received_at from the email Date header
            try:
                from email.utils import parsedate_to_datetime
                received_at = parsedate_to_datetime(date_str)
                # Make naive UTC for SQLAlchemy
                received_at = received_at.replace(tzinfo=None)
            except Exception:
                received_at = datetime.utcnow()

            logger.info("Processing RMA #%s from %s (subject: %s)", rma_number, sender, subject)

            # Walk all MIME parts looking for image attachments and inline images
            attachments_found = 0
            for part in msg.walk():
                content_type = part.get_content_type()
                content_disposition = part.get('Content-Disposition', '')

                # Skip container and plain-text parts immediately
                if content_type.startswith('multipart/') or content_type.startswith('text/'):
                    continue

                # get_filename() checks both Content-Disposition filename= and
                # Content-Type name= params, covering most inline images
                raw_filename = part.get_filename()

                if raw_filename:
                    # Decode RFC2047-encoded filenames
                    try:
                        raw_filename = str(make_header(decode_header(raw_filename)))
                    except Exception:
                        pass
                elif content_type.startswith('image/'):
                    # Pasted/CID-referenced inline image with no explicit filename.
                    # Build a name from Content-ID (e.g. <image001.jpg@...>) or a timestamp.
                    cid = part.get('Content-ID', '').strip('<>').split('@')[0]
                    ext = content_type.split('/')[-1].split(';')[0].strip()  # e.g. "jpeg"
                    ext = 'jpg' if ext == 'jpeg' else ext
                    raw_filename = f"{cid}.{ext}" if cid else f"inline_image.{ext}"
                    logger.debug("Inline image without filename; using generated name: %s", raw_filename)
                else:
                    # Non-image part with no filename — not relevant
                    continue

                if not _is_allowed_attachment(raw_filename):
                    logger.debug("Skipping non-image attachment: %s", raw_filename)
                    continue

                safe_filename = _sanitize_filename(raw_filename)
                # Prefix with timestamp to avoid collisions
                timestamp_prefix = datetime.utcnow().strftime('%Y%m%d_%H%M%S_')
                final_filename = timestamp_prefix + safe_filename

                # Build target directory: upload_base_dir/RMA1234567/
                rma_dir = os.path.join(upload_base_dir, rma_number)
                os.makedirs(rma_dir, exist_ok=True)

                file_path = os.path.join(rma_dir, final_filename)
                payload = part.get_payload(decode=True)
                if payload is None:
                    continue

                with open(file_path, 'wb') as f:
                    f.write(payload)

                # filepath stored relative to upload_base_dir so it stays portable
                relative_path = os.path.join(rma_number, final_filename)

                results.append({
                    'rma_number':    rma_number,
                    'filename':      final_filename,
                    'filepath':      relative_path,
                    'email_from':    sender,
                    'email_subject': subject,
                    'received_at':   received_at,
                })

                attachments_found += 1
                logger.info("  Saved attachment: %s", file_path)

            if attachments_found == 0:
                logger.warning("RMA email found but no image attachments: %s", subject)

            # Mark as read regardless of whether attachments were found
            if mark_as_read:
                conn.store(msg_id, '+FLAGS', '\\Seen')

    finally:
        try:
            conn.logout()
        except Exception:
            pass

    logger.info("Done. %d image(s) saved.", len(results))
    return results


def process_credit_emails_graph(upload_base_dir):
    """
    Connect to Microsoft Graph API, find unread emails with an RMA number in the
    subject, save attachments (performing HEIC->JPG conversion), and return
    a list of CreditImage field dicts.
    """
    client_id     = os.environ.get('GRAPH_CLIENT_ID')
    client_secret = os.environ.get('GRAPH_CLIENT_SECRET')
    tenant_id     = os.environ.get('GRAPH_TENANT_ID')
    user_email    = os.environ.get('EMAIL_ADDRESS')

    if not all([client_id, client_secret, tenant_id, user_email]):
        raise ValueError("GRAPH_CLIENT_ID, GRAPH_CLIENT_SECRET, GRAPH_TENANT_ID, and EMAIL_ADDRESS must be set.")

    results = []
    
    # 1. Authenticate via MSAL (Client Credentials Flow)
    authority = f"https://login.microsoftonline.com/{tenant_id}"
    app = msal.ConfidentialClientApplication(client_id, authority=authority, client_credential=client_secret)
    
    # Permissions needed: Mail.Read, Mail.ReadWrite (to mark read)
    token_response = app.acquire_token_for_client(scopes=["https://graph.microsoft.com/.default"])
    
    if "access_token" not in token_response:
        logger.error("Could not acquire Microsoft Graph token: %s", token_response.get("error_description"))
        return results

    headers = {'Authorization': f'Bearer {token_response["access_token"]}'}
    base_url = f"https://graph.microsoft.com/v1.0/users/{user_email}"

    # 2. Search for unread emails (isRead eq false) containing "RMA"
    # Note: Filter must use single quotes.
    query = "isRead eq false and (contains(subject, 'RMA') or contains(subject, 'rma'))"
    search_url = f"{base_url}/messages?$filter={query}&$select=id,subject,from,receivedDateTime,hasAttachments"

    try:
        resp = requests.get(search_url, headers=headers)
        resp.raise_for_status()
        messages = resp.json().get('value', [])
        logger.info("Found %d potential RMA emails via Graph API.", len(messages))

        for msg in messages:
            subject = msg.get('subject', '')
            rma_match = RMA_PATTERN.search(subject)
            if not rma_match:
                continue

            rma_number = rma_match.group(1)
            msg_id = msg['id']
            sender = msg['from']['emailAddress']['address']
            
            # Graph returns ISO 8601 string
            received_str = msg['receivedDateTime']
            try:
                # 2024-02-23T20:02:47Z -> datetime
                received_at = datetime.fromisoformat(received_str.replace('Z', '+00:00'))
                received_at = received_at.replace(tzinfo=None)
            except Exception:
                received_at = datetime.utcnow()

            logger.info("Processing Graph RMA #%s from %s", rma_number, sender)

            # 3. Fetch Attachments
            attach_url = f"{base_url}/messages/{msg_id}/attachments"
            att_resp = requests.get(attach_url, headers=headers)
            att_resp.raise_for_status()
            attachments = att_resp.json().get('value', [])

            for att in attachments:
                # We only care about file attachments
                if att.get('@odata.type') != '#microsoft.graph.fileAttachment':
                    continue

                raw_name = att.get('name', 'attachment')
                if not _is_allowed_attachment(raw_name):
                    continue

                content_bytes = att.get('contentBytes')
                if not content_bytes:
                    continue

                import base64
                payload = base64.b64decode(content_bytes)

                # Prepare filename
                safe_name = _sanitize_filename(raw_name)
                timestamp_prefix = datetime.utcnow().strftime('%Y%m%d_%H%M%S_')
                final_name = timestamp_prefix + safe_name
                
                rma_dir = os.path.join(upload_base_dir, rma_number)
                os.makedirs(rma_dir, exist_ok=True)
                
                file_path = os.path.join(rma_dir, final_name)
                ext = os.path.splitext(final_name)[1].lower()

                # 4. HEIC Conversion Logic
                if ext in {'.heic', '.heif'}:
                    try:
                        # Convert to JPG
                        import io
                        heif_file = pillow_heif.read_heif(io.BytesIO(payload))
                        image = Image.frombytes(heif_file.mode, heif_file.size, heif_file.data, "raw", heif_file.mode, heif_file.stride)
                        
                        # Change extension to jpg
                        final_name = os.path.splitext(final_name)[0] + ".jpg"
                        file_path = os.path.join(rma_dir, final_name)
                        
                        image.save(file_path, "JPEG", quality=90)
                        logger.info("  Converted %s -> %s", raw_name, final_name)
                    except Exception as e:
                        logger.error("  HEIC conversion failed for %s: %s", raw_name, e)
                        # Fallback: save as-is if conversion fails
                        with open(file_path, 'wb') as f:
                            f.write(payload)
                else:
                    # Save standard file
                    with open(file_path, 'wb') as f:
                        f.write(payload)

                results.append({
                    'rma_number':    rma_number,
                    'filename':      final_name,
                    'filepath':      os.path.join(rma_number, final_name),
                    'email_from':    sender,
                    'email_subject': subject,
                    'received_at':   received_at,
                })

            # 4. Mark as Read (PATCH message)
            requests.patch(f"{base_url}/messages/{msg_id}", headers=headers, json={'isRead': True})

    except Exception as e:
        logger.error("Graph API sync error: %s", e)
        raise

    return results
