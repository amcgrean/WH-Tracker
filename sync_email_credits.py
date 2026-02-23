"""
sync_email_credits.py
----------------------
Standalone script: polls the inbox for RMA credit emails, saves
attachments to disk, and records them in the database.

Run manually:
    python sync_email_credits.py

Or schedule via Windows Task Scheduler (see run_email_sync.bat).

Requires .env with:
    EMAIL_ADDRESS=amcgrean@beisserlumber.com
    EMAIL_PASSWORD=<your M365 password or app password>
    IMAP_SERVER=outlook.office365.com   (optional, this is the default)
    UPLOAD_FOLDER=uploads/credits       (optional, defaults shown)
"""

import os
import sys
import logging
from dotenv import load_dotenv

# Load .env before anything else
load_dotenv()

# Set up logging — writes to console and to a log file
log_dir = os.path.join(os.path.dirname(__file__), 'logs')
os.makedirs(log_dir, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s  %(levelname)-8s %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(os.path.join(log_dir, 'email_sync.log'), encoding='utf-8'),
    ]
)
logger = logging.getLogger(__name__)

# Bootstrap Flask app so we can use SQLAlchemy outside a request
from app import create_app
from app.extensions import db
from app.Models.models import CreditImage
from app.Services.email_service import process_credit_emails

app = create_app()

with app.app_context():
    # Resolve the upload folder (absolute path)
    upload_folder_rel = os.environ.get('UPLOAD_FOLDER', 'uploads/credits')
    upload_base_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), upload_folder_rel)
    os.makedirs(upload_base_dir, exist_ok=True)

    logger.info("Starting credit email sync...")
    logger.info("Upload directory: %s", upload_base_dir)

    try:
        new_records = process_credit_emails(upload_base_dir, mark_as_read=True)
    except Exception as exc:
        logger.error("Email polling failed: %s", exc, exc_info=True)
        sys.exit(1)

    if not new_records:
        logger.info("No new RMA credit emails found.")
    else:
        saved = 0
        for record in new_records:
            try:
                img = CreditImage(
                    rma_number    = record['rma_number'],
                    filename      = record['filename'],
                    filepath      = record['filepath'],
                    email_from    = record['email_from'],
                    email_subject = record['email_subject'],
                    received_at   = record['received_at'],
                )
                db.session.add(img)
                db.session.commit()
                saved += 1
                logger.info("  DB record saved: RMA #%s — %s", record['rma_number'], record['filename'])
            except Exception as exc:
                db.session.rollback()
                logger.error("  Failed to save DB record for %s: %s", record.get('filename'), exc)

        logger.info("Sync complete. %d/%d image(s) recorded.", saved, len(new_records))
