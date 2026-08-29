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
UPDATED: Added FORCE_DATE environment variable to allow processing emails from a specific past date
UPDATED: Added pre-marking of "Not Sent" BEFORE processing emails to ensure all employees get marked even if no emails received
"""

import logging
import time
import sys
import os
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from config import (
    SALES_EMAIL_MAP, SALES_EMPLOYEES,
    SALES_DEADLINE_HOUR, SALES_DEADLINE_MINUTE,
    SALES_SPREADSHEET_ID,
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
        
        # Log Sheet ID for debugging
        logger.info(f"📊 Using Sales Spreadsheet ID: {SALES_SPREADSHEET_ID}")
        logger.info(f"📊 Sheet ID length: {len(SALES_SPREADSHEET_ID)}")

        # Graceful handling of Sheets connection failures
        try:
            self.sheets = SheetsService()
            logger.info("✅ SheetsService initialized successfully")
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
            logger.info(f"⏭️ Already marked 'Not Sent' for {dept} on {date_str}")
            return

        logger.info(f"📝 Marking all {dept} employees as 'Not Sent' for {date_str}")
        try:
            self.sheets.mark_all_as_not_sent(dept, date_str)
            ReportProcessor._date_marked_not_sent[key] = True
            logger.info(f"✅ Successfully marked all {dept} employees as 'Not Sent' for {date_str}")
        except Exception as e:
            logger.error(f"❌ Failed to mark 'Not Sent' for {dept} on {date_str}: {e}")

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

        logger.info(f"📧 Processing email: ID={email_id[:10]}..., From={sender_email}")

        if self.tracker.is_duplicate(email_hash):
            logger.info(f"🚫 Skipping duplicate email (already processed globally): {subject}")
            return {"status": "SKIPPED_DUPLICATE"}

        if email_id in PROCESSED_EMAILS:
            logger.info(f"⏭️ Already processed in this run: {email_id}")
            return {"status": "SKIPPED_RUN"}

        def _fail(reason: str, dept="", emp="", date="") -> Dict:
            logger.error(f"❌ FAILED: {reason} | Dept={dept}, Emp={emp}, Date={date}")
            self.tracker.log_status(
                preview, "FAILED", email_id, dept, emp, date, reason,
                processing_time=time.time() - t0, sender_email=sender_email,
                sender_name=emp, received_time=received_at,
            )
            return {"status": "FAILED", "reason": reason}

        def _success(dept: str, emp: str, date_str: str) -> Dict:
            logger.info(f"✅ SUCCESS: Dept={dept}, Emp={emp}, Date={date_str}")
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
            logger.info(f"📅 Email date: {date_str}, Today: {datetime.now().strftime('%d-%m-%Y')}")

            # ============================================================
            # 🔥 Date filter logic with FORCE_DATE override
            # ============================================================
            force_date = os.environ.get("FORCE_DATE", "").strip()
            
            if force_date:
                # If FORCE_DATE is set, only process emails matching that exact date
                logger.info(f"🔧 FORCE_DATE is set to: {force_date}")
                if date_str != force_date:
                    logger.info(f"⏭️ Skipping email from {date_str} (FORCE_DATE={force_date})")
                    self.tracker.mark_processed(email_hash)
                    return {"status": "SKIPPED_OLD_DATE", "reason": f"Date {date_str} != FORCE_DATE"}
                else:
                    logger.info(f"✅ Email date {date_str} matches FORCE_DATE. Processing...")
            else:
                # ✅ DEFAULT: ONLY process today's emails
                if not self._is_today_date(date_str):
                    logger.info(f"⏭️ Skipping email from {date_str} (not today) - will remain unread")
                    self.tracker.mark_processed(email_hash)
                    return {"status": "SKIPPED_OLD_DATE", "reason": f"Email date {date_str} is not today"}
                else:
                    logger.info(f"✅ Email date {date_str} is today. Processing...")

            # ============================================================
            # END OF DATE FILTER
            # ============================================================

            # Mark "Not Sent" for all employees on this date
            self._mark_all_as_not_sent_for_date(dept, date_str)

            if self._check_already_in_sheet(dept, canonical_name, date_str):
                logger.info(f"✅ Employee {canonical_name} already has data in sheet for {date_str} → skipping")
                self.tracker.mark_processed(email_hash)
                return {"status": "SKIPPED_SHEET"}

            email_data = self.parser.parse_email(body, sender_email)
            if not email_data:
                return _fail("Email body parsing failed", dept=dept, emp=canonical_name, date=date_str)

            logger.info(f"📊 Parsed data: {email_data}")

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
            logger.info(f"📝 Added to write buffer: Row={row_num}, Data={email_data}")

            return _success(dept, canonical_name, date_str)

        except Exception as exc:
            log_error(exc, {"email_id": email_id})
            return _fail(f"Error: {exc}")

    def _flush_writes(self) -> None:
        if not self._write_buffer:
            logger.info("📭 No writes to flush - buffer is empty")
            return
        
        logger.info(f"📤 Flushing {len(self._write_buffer)} write batches...")
        for (dept, date_str), entries in self._write_buffer.items():
            try:
                logger.info(f"📤 Writing {len(entries)} entries for {dept}/{date_str}")
                self.sheets.write_batch(dept, date_str, entries)
                logger.info(f"✅ Flushed {len(entries)} writes for {dept}/{date_str}")
            except Exception as exc:
                logger.error(f"❌ Failed to flush writes: {exc}")
        self._write_buffer.clear()

    def run(self) -> List[Dict]:
        global PROCESSED_EMAILS
        PROCESSED_EMAILS = set()
        ReportProcessor._date_marked_not_sent = {}

        logger.info("=" * 60)
        logger.info("🚀 Report Processor started")
        
        # Determine which date to process (today or FORCE_DATE)
        force_date = os.environ.get("FORCE_DATE", "").strip()
        if force_date:
            today_date = force_date
            logger.info(f"🔧 FORCE_DATE override: Processing emails for {force_date}")
        else:
            today_date = datetime.now().strftime("%d-%m-%Y")
            logger.info(f"📅 Today's date: {today_date}")
        
        dept = "Sales"
        
        logger.info(f"👥 Expected employees: {len(SALES_EMPLOYEES)}")
        logger.info(f"📧 Employee emails: {list(SALES_EMAIL_MAP.keys())}")

        # ✅ STEP 1: PRE-MARK all employees as "Not Sent" for the target date
        try:
            logger.info(f"📝 Pre-marking all {dept} employees as 'Not Sent' for {today_date}")
            
            # Create sheet and ensure all employees have rows
            self.sheets.ensure_date_for_all_employees(dept, today_date)
            logger.info(f"✅ Ensured all employees have rows for {today_date}")
            
            # Ensure status column exists
            self.sheets.ensure_status_column(dept, today_date)
            logger.info(f"✅ Ensured status column exists for {today_date}")
            
            # Mark all as "Not Sent"
            self._mark_all_as_not_sent_for_date(dept, today_date)
            logger.info(f"✅ Pre-marked all employees as 'Not Sent' for {today_date}")
            
            # Verify sheet has data
            try:
                ws = self.sheets._get_worksheet(dept, today_date)
                all_data = ws.get_all_values()
                logger.info(f"🔍 Sheet '{ws.title}' has {len(all_data)} rows")
                if len(all_data) > 1:
                    logger.info(f"🔍 First data row: {all_data[1] if len(all_data) > 1 else 'None'}")
            except Exception as e:
                logger.warning(f"Could not verify sheet contents: {e}")
                
        except Exception as e:
            logger.error(f"❌ Failed to pre-mark 'Not Sent' for {today_date}: {e}")
            import traceback
            traceback.print_exc()

        # ✅ STEP 2: Fetch and process emails
        logger.info("📬 Fetching emails from Gmail...")
        emails = self.gmail.fetch_emails()
        logger.info(f"📬 Fetched {len(emails)} email(s) to process")

        if len(emails) == 0:
            logger.info("⚠️ No emails found to process. This is the likely reason no data was written.")
            logger.info("   Possible reasons:")
            logger.info("   1. No employees have sent emails today")
            logger.info("   2. Emails have already been read/marked as read")
            logger.info("   3. Emails are not from allowed senders")
            logger.info("   4. Gmail API is not properly connected")

        results = []
        for idx, email in enumerate(emails, 1):
            logger.info(f"📧 Processing {idx}/{len(emails)}")
            results.append(self.process_email(email))

        # ✅ STEP 3: Flush all writes to Google Sheets
        self._flush_writes()

        # ✅ STEP 4: Finalize - Re-mark "Not Sent" for any remaining employees
        try:
            logger.info(f"📝 Finalizing 'Not Sent' marks for {today_date}")
            self._mark_all_as_not_sent_for_date(dept, today_date)
            logger.info(f"✅ Finalized 'Not Sent' marks for {today_date}")
        except Exception as e:
            logger.error(f"❌ Failed to finalize 'Not Sent' for {today_date}: {e}")

        success = sum(1 for r in results if r.get("status") == "SUCCESS")
        failed = sum(1 for r in results if r.get("status") == "FAILED")
        skipped = sum(1 for r in results if r.get("status") in ["SKIPPED_DUPLICATE", "SKIPPED_RUN", "SKIPPED_SHEET", "SKIPPED_OLD_DATE"])

        logger.info("=" * 60)
        logger.info(f"📊 Run complete → SUCCESS={success}  FAILED={failed}  SKIPPED={skipped}")
        
        if success == 0 and failed == 0 and skipped == 0 and len(emails) == 0:
            logger.warning("⚠️⚠️⚠️ NO EMAILS FOUND AND NO DATA WRITTEN ⚠️⚠️⚠️")
            logger.warning("Please check:")
            logger.warning("  1. Employees have sent emails to the Gmail account")
            logger.warning("  2. The Gmail account is properly configured")
            logger.warning("  3. The Gmail API has access to read emails")
            logger.warning("  4. The service account has access to the Google Sheet")
        elif success > 0:
            logger.info(f"✅ {success} emails were successfully processed and written to the sheet!")
        elif success == 0 and len(emails) > 0:
            logger.warning("⚠️ Emails were found but none were successfully processed. Check error logs above.")
        
        logger.info("=" * 60)
        return results


if __name__ == "__main__":
    processor = ReportProcessor()
    processor.run()
