"""
main.py — Production pipeline orchestrator
BRANCH: THANE NEW - Sales Only
Always writes email body values.
Duplicate check is FIRST to prevent re-processing same email.
NOW WITH: Sheet check before processing to prevent duplicate writes
UPDATED: Removed ALL status messages from Report Status column (always blank except Not Sent)
UPDATED: Added logic to mark Sales employees as "Not Sent" if they submit after 09:00 PM IST
UPDATED: Added graceful error handling for Sheets connection failures
UPDATED: Removed HR references (Sales only branch)
"""

import logging
import time
import sys
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from config import (
    SALES_EMAIL_MAP, SALES_EMPLOYEES,
    SALES_DEADLINE_HOUR, SALES_DEADLINE_MINUTE,
)
from error_handler import BaseProcessingError, log_error
from gmail_reader import GmailReader
from gemini_parser import GeminiParser
from sheets_service import SheetsService
from tracker import Tracker
from utils import (
    extract_email_address,
    received_timestamp_to_date,
)
from validator import DataValidator
from vision_parser import VisionParser

print("DEBUG: main.py started", flush=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

PROCESSED_EMAILS = set()


class ReportProcessor:
    _date_marked_not_sent: Dict[str, bool] = {}

    def __init__(self):
        print("DEBUG: Initialising ReportProcessor", flush=True)
        logger.info("Initialising ReportProcessor...")

        # Graceful handling of Sheets connection failures
        try:
            self.sheets = SheetsService()
        except Exception as e:
            logger.error(f"❌ Failed to connect to Google Sheets: {e}")
            logger.error("⚠️ The workflow will exit with failure. Please check:")
            logger.error("   1. Google Sheets API is enabled")
            logger.error("   2. Service account has access to the spreadsheet")
            logger.error("   3. Google Sheets is not experiencing an outage")
            logger.error("   4. SALES_SPREADSHEET_ID is correct in secrets")
            sys.exit(1)

        self.gmail = GmailReader()
        self.parser = GeminiParser()
        self.vision = VisionParser()
        self.tracker = Tracker()
        self.validator = DataValidator()
        self._write_buffer: Dict[Tuple[str, str], List[Tuple[int, Dict]]] = {}

    def _match_sender_to_department(self, sender_email: str) -> Tuple[Optional[str], Optional[str]]:
        sender_lower = sender_email.lower()

        for email, name in SALES_EMAIL_MAP.items():
            if email.lower() == sender_lower:
                return ("Sales", name)

        return (None, None)

    def _check_already_in_sheet(self, department: str, employee_name: str, date_str: str) -> bool:
        try:
            row_num = self.sheets.find_employee_row(department, date_str, employee_name)
            if not row_num:
                return False

            ws = self.sheets._get_worksheet(department, date_str)
            row_data = ws.row_values(row_num)

            mapping = self.sheets.get_column_mapping(department)
            for field, col in mapping.items():
                if field not in ("Date", "Employee Name", "Report Status"):
                    if col - 1 < len(row_data) and row_data[col - 1].strip():
                        val = row_data[col - 1].strip()
                        if val not in ["", "0", "00:00:00", "Not Sent", "Invalid"]:
                            logger.info(f"Employee {employee_name} already has data in sheet for {date_str}: {field}={val}")
                            return True

            return False
        except Exception as e:
            logger.warning(f"Error checking sheet for {employee_name}: {e}")
            return False

    def _is_today_date(self, date_str: str) -> bool:
        try:
            email_date = datetime.strptime(date_str, "%d-%m-%Y").date()
            today_date = datetime.now().date()
            return email_date == today_date
        except Exception as e:
            logger.warning(f"Error comparing dates: {e}")
            return False

    def _is_after_sales_deadline(self, received_time: datetime) -> bool:
        """Check if the received time is after the Sales deadline (09:00 PM IST)"""
        hour = received_time.hour
        minute = received_time.minute

        if hour > SALES_DEADLINE_HOUR:
            return True
        elif hour == SALES_DEADLINE_HOUR and minute >= SALES_DEADLINE_MINUTE:
            return True
        return False

    def _mark_all_as_not_sent_for_date(self, dept: str, date_str: str) -> None:
        key = f"{dept}_{date_str}"
        if key in ReportProcessor._date_marked_not_sent:
            return

        logger.info(f"📝 Marking all {dept} employees as 'Not Sent' for {date_str}")
        try:
            self.sheets.mark_all_as_not_sent(dept, date_str)
            ReportProcessor._date_marked_not_sent[key] = True
        except Exception as e:
            logger.error(f"Failed to mark 'Not Sent' for {dept} on {date_str}: {e}")

    def process_email(self, email: Dict) -> Dict:
        t0 = time.time()
        email_id = email.get("id", "")
        subject = email.get("subject", "")
        body = email.get("body", "")
        attachments = email.get("attachments", [])
        email_hash = email.get("hash", "")
        sender_email = email.get("sender_email", "")
        received_at = email.get("received_at", datetime.now())
        received_ms = email.get("received_ms", 0)
        preview = (subject or body)[:120]

        if self.tracker.is_duplicate(email_hash):
            logger.info(f"🚫 Skipping duplicate email (already processed globally): {subject}")
            return {"status": "SKIPPED_DUPLICATE"}

        if email_id in PROCESSED_EMAILS:
            logger.info(f"⏭️ Already processed in this run: {email_id}")
            return {"status": "SKIPPED_RUN"}

        logger.info(f"📧 Processing: {sender_email}")

        def _fail(reason: str, dept="", emp="", date="") -> Dict:
            self.tracker.log_status(
                preview, "FAILED", email_id, dept, emp, date, reason,
                processing_time=time.time() - t0, sender_email=sender_email,
                sender_name=emp, received_time=received_at,
            )
            return {"status": "FAILED", "reason": reason}

        def _success(dept: str, emp: str, date_str: str) -> Dict:
            PROCESSED_EMAILS.add(email_id)
            self.tracker.mark_processed(email_hash)
            self.tracker.log_status(
                preview, "SUCCESS", email_id, dept, emp, date_str,
                processing_time=time.time() - t0, sender_email=sender_email,
                sender_name=emp, received_time=received_at,
            )
            return {"status": "SUCCESS", "department": dept, "employee": emp, "date": date_str}

        try:
            dept, canonical_name = self._match_sender_to_department(sender_email)
            if dept is None:
                return _fail(f"Sender '{sender_email}' not in department maps")

            date_str = received_timestamp_to_date(received_ms) if received_ms else received_at.strftime("%d-%m-%Y")

            self._mark_all_as_not_sent_for_date(dept, date_str)

            if not self._is_today_date(date_str):
                logger.info(f"⏭️ Skipping email from {date_str} (not today's date) - will remain unread")
                self.tracker.mark_processed(email_hash)
                return {"status": "SKIPPED_OLD_DATE", "reason": f"Email date {date_str} is not today"}

            if self._check_already_in_sheet(dept, canonical_name, date_str):
                logger.info(f"✅ Employee {canonical_name} already has data in sheet for {date_str} → skipping")
                self.tracker.mark_processed(email_hash)
                return {"status": "SKIPPED_SHEET"}

            email_data = self.parser.parse_email(body, sender_email)
            if not email_data:
                return _fail("Email body parsing failed", dept=dept, emp=canonical_name, date=date_str)

            email_data["department"] = dept
            email_data["employee_name"] = canonical_name
            email_data["date"] = date_str

            ok, field_err = self.validator.validate_required_fields(email_data, dept)
            if not ok:
                return _fail(field_err, dept=dept, emp=canonical_name, date=date_str)

            # Set status based on Sales deadline rule
            report_status = ""

            if dept == "Sales":
                if self._is_after_sales_deadline(received_at):
                    report_status = "Not Sent"
                    logger.info(f"⚠️ Sales employee {canonical_name} submitted after {SALES_DEADLINE_HOUR:02d}:00 - marked as 'Not Sent'")
                else:
                    report_status = ""

            email_data["report_status"] = report_status

            self.sheets.ensure_date_for_all_employees(dept, date_str)
            self.sheets.ensure_status_column(dept, date_str)
            row_num = self.sheets.find_employee_row(dept, date_str, canonical_name)

            if not row_num:
                return _fail(f"Row not found for {canonical_name}", dept=dept, emp=canonical_name, date=date_str)

            key = (dept, date_str)
            self._write_buffer.setdefault(key, []).append((row_num, email_data))

            return _success(dept, canonical_name, date_str)

        except Exception as exc:
            log_error(exc, {"email_id": email_id})
            return _fail(f"Error: {exc}")

    def _flush_writes(self) -> None:
        if not self._write_buffer:
            return
        for (dept, date_str), entries in self._write_buffer.items():
            try:
                self.sheets.write_batch(dept, date_str, entries)
                logger.info(f"Flushed {len(entries)} writes for {dept}/{date_str}")
            except Exception as exc:
                logger.error(f"Failed to flush writes: {exc}")
        self._write_buffer.clear()

    def run(self) -> List[Dict]:
        global PROCESSED_EMAILS
        PROCESSED_EMAILS = set()
        ReportProcessor._date_marked_not_sent = {}

        logger.info("=" * 60)
        logger.info("Report Processor started")

        emails = self.gmail.fetch_emails()
        logger.info(f"📬 Fetched {len(emails)} email(s) to process")

        results = []
        for idx, email in enumerate(emails, 1):
            logger.info(f"Processing {idx}/{len(emails)}")
            results.append(self.process_email(email))

        self._flush_writes()

        success = sum(1 for r in results if r.get("status") == "SUCCESS")
        failed = sum(1 for r in results if r.get("status") == "FAILED")
        skipped = sum(1 for r in results if r.get("status") in ["SKIPPED_DUPLICATE", "SKIPPED_RUN", "SKIPPED_SHEET", "SKIPPED_OLD_DATE"])

        logger.info(f"Run complete → SUCCESS={success}  FAILED={failed}  SKIPPED={skipped}")
        logger.info("=" * 60)
        return results


if __name__ == "__main__":
    processor = ReportProcessor()
    processor.run()
