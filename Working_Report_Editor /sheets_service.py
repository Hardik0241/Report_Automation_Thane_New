"""
sheets_service.py — Google Sheets operations with Calibri font, size 13, center alignment
BRANCH: THANE NEW - Sales Only
DEBUG VERSION - Added extensive debug logging to pinpoint connection failures
"""

import logging
import json
import os
import re
import time
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import gspread
from google.oauth2 import service_account

from config import (
    DATE_IN_SUBJECT_FORMAT,
    SALES_COLUMN_MAPPING,
    SALES_EMPLOYEES,
    SALES_HEADERS,
    SALES_SPREADSHEET_ID,
    SHEET_NAME_FORMAT,
)
from error_handler import with_retry

logger = logging.getLogger(__name__)
_SCOPES = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]


def _get_credentials():
    """Get credentials from environment variable with debug logging."""
    logger.info("🔍 DEBUG: _get_credentials() called")
    
    # Check if GOOGLE_CREDENTIALS environment variable exists
    creds_json = os.environ.get("GOOGLE_CREDENTIALS", "")
    logger.info(f"🔍 DEBUG: GOOGLE_CREDENTIALS env var exists: {bool(creds_json)}")
    logger.info(f"🔍 DEBUG: GOOGLE_CREDENTIALS length: {len(creds_json)} characters")
    
    if creds_json:
        try:
            logger.info("🔍 DEBUG: Attempting to parse GOOGLE_CREDENTIALS JSON...")
            creds_dict = json.loads(creds_json)
            logger.info(f"🔍 DEBUG: JSON parsed successfully!")
            logger.info(f"🔍 DEBUG: client_email = {creds_dict.get('client_email', 'NOT FOUND')}")
            logger.info(f"🔍 DEBUG: project_id = {creds_dict.get('project_id', 'NOT FOUND')}")
            logger.info(f"🔍 DEBUG: private_key length = {len(creds_dict.get('private_key', ''))} characters")
            
            logger.info("✅ Loading Service Account credentials from GOOGLE_CREDENTIALS env var")
            return service_account.Credentials.from_service_account_info(
                creds_dict, scopes=_SCOPES
            )
        except json.JSONDecodeError as e:
            logger.error(f"❌ DEBUG: Failed to parse GOOGLE_CREDENTIALS JSON: {e}")
            logger.error(f"❌ DEBUG: First 100 characters of JSON: {creds_json[:100]}...")
            raise Exception(f"Invalid GOOGLE_CREDENTIALS JSON: {e}")
        except Exception as e:
            logger.error(f"❌ DEBUG: Failed to create credentials: {e}")
            raise

    # Check if credentials.json file exists (fallback)
    if os.path.exists("credentials.json"):
        logger.info("✅ Loading from credentials.json file")
        return service_account.Credentials.from_service_account_file("credentials.json", scopes=_SCOPES)

    logger.error("❌ DEBUG: No valid credentials found!")
    logger.error("❌ DEBUG: Check that GOOGLE_CREDENTIALS secret is set correctly")
    raise Exception("No valid credentials found")


def _get_gspread_client() -> gspread.Client:
    """Get gspread client with timeout."""
    logger.info("🔍 DEBUG: _get_gspread_client() called")
    try:
        creds = _get_credentials()
        logger.info("🔍 DEBUG: Credentials obtained, authorizing gspread...")
        client = gspread.authorize(creds)
        logger.info("🔍 DEBUG: Setting client timeout to 30 seconds...")
        client.timeout = 30
        logger.info("✅ Gspread client created successfully")
        return client
    except Exception as e:
        logger.error(f"❌ DEBUG: Failed to create gspread client: {e}")
        raise


def _connect_with_retry(max_retries: int = 5, initial_delay: int = 2) -> Tuple[gspread.Client, object]:
    """
    Attempt to connect to Google Sheets with retry logic and extensive debug logging.
    """
    logger.info("🔍 DEBUG: _connect_with_retry() called")
    logger.info(f"🔍 DEBUG: max_retries={max_retries}, initial_delay={initial_delay}")
    
    last_error = None
    
    for attempt in range(max_retries):
        try:
            logger.info(f"🔄 Connecting to Google Sheets (attempt {attempt + 1}/{max_retries})...")
            
            logger.info("🔍 DEBUG: Calling _get_gspread_client()...")
            client = _get_gspread_client()
            logger.info("✅ DEBUG: Client obtained successfully")

            # Try to open the Sales spreadsheet
            logger.info(f"🔍 DEBUG: Attempting to open spreadsheet with ID: {SALES_SPREADSHEET_ID}")
            logger.info(f"🔍 DEBUG: SALES_SPREADSHEET_ID length: {len(SALES_SPREADSHEET_ID)} characters")
            
            sales_ss = client.open_by_key(SALES_SPREADSHEET_ID)
            
            # Verify connection by fetching spreadsheet title
            sales_title = sales_ss.title
            logger.info(f"✅ Successfully connected to Sales spreadsheet: '{sales_title}'")
            
            return client, sales_ss
            
        except gspread.exceptions.APIError as e:
            last_error = e
            error_msg = str(e)
            logger.error(f"❌ DEBUG: APIError on attempt {attempt + 1}: {error_msg[:200]}...")
            
            # Check for specific error types
            if "404" in error_msg:
                logger.error(f"❌ DEBUG: Spreadsheet NOT FOUND (404). Check that:")
                logger.error(f"   - The Sheet ID is correct: {SALES_SPREADSHEET_ID}")
                logger.error(f"   - The Service Account has access to the sheet")
                logger.error(f"   - The sheet exists and is not deleted")
            elif "403" in error_msg:
                logger.error(f"❌ DEBUG: Permission DENIED (403). Check that:")
                logger.error(f"   - The Service Account has EDITOR access to the sheet")
                logger.error(f"   - Google Sheets API is enabled")
            elif "429" in error_msg:
                logger.error(f"⚠️ DEBUG: Rate limit (429) - will retry")
            elif "503" in error_msg or "unavailable" in error_msg.lower():
                logger.error(f"⚠️ DEBUG: Service unavailable (503) - will retry")
            else:
                logger.error(f"❌ DEBUG: Other API error: {error_msg[:200]}...")
                
        except Exception as e:
            last_error = e
            logger.error(f"❌ DEBUG: Exception on attempt {attempt + 1}: {type(e).__name__}: {e}")
            
        # Check if we should retry
        if attempt < max_retries - 1:
            delay = initial_delay * (2 ** attempt)
            logger.info(f"⏳ Retrying in {delay} seconds...")
            time.sleep(delay)
        else:
            logger.error(f"❌ Failed to connect after {max_retries} attempts")
    
    # If we get here, all retries failed
    logger.error(f"❌ DEBUG: All retries exhausted. Last error: {last_error}")
    raise Exception(f"Failed to connect to Google Sheets after {max_retries} attempts. Last error: {last_error}")


class SheetsService:
    def __init__(self):
        logger.info("🔍 DEBUG: SheetsService.__init__() called")
        
        # Use retry logic for connection
        try:
            logger.info("🔍 DEBUG: Calling _connect_with_retry()...")
            client, sales_ss = _connect_with_retry()
            logger.info("✅ DEBUG: Connection successful!")
        except Exception as e:
            logger.error(f"❌ DEBUG: Connection failed in __init__: {e}")
            raise
        
        self._sales_ss = sales_ss
        self._client = client
        
        logger.info("✅ Connected to Sales spreadsheet")
        self._emp_cache: Dict[Tuple[str, str], Dict[str, int]] = {}
        self._ws_cache: Dict[Tuple[str, str], gspread.Worksheet] = {}
        self._worksheet_data_cache: Dict[Tuple[str, str], List[List[str]]] = {}
        self._cache_timestamp: Dict[Tuple[str, str], datetime] = {}
        self._cache_ttl_seconds = 60
        self._date_marked_not_sent: set = set()

    def _spreadsheet(self, department: str):
        return self._sales_ss

    @staticmethod
    def sheet_name(date_str: str) -> str:
        return datetime.strptime(date_str, DATE_IN_SUBJECT_FORMAT).strftime(SHEET_NAME_FORMAT)
    
    def get_column_mapping(self, department: str) -> Dict:
        return SALES_COLUMN_MAPPING

    def _get_cached_worksheet_data(self, department: str, date_str: str) -> List[List[str]]:
        key = (department, date_str)
        now = datetime.now()
        
        if key in self._worksheet_data_cache and key in self._cache_timestamp:
            if (now - self._cache_timestamp[key]).seconds < self._cache_ttl_seconds:
                return self._worksheet_data_cache[key]
        
        ws = self._get_worksheet(department, date_str)
        data = ws.get_all_values()
        self._worksheet_data_cache[key] = data
        self._cache_timestamp[key] = now
        return data
    
    def _invalidate_cache(self, department: str, date_str: str) -> None:
        key = (department, date_str)
        if key in self._worksheet_data_cache:
            del self._worksheet_data_cache[key]
        if key in self._cache_timestamp:
            del self._cache_timestamp[key]

    def _apply_formatting(self, ws: gspread.Worksheet, range_str: str = None) -> None:
        try:
            if range_str is None:
                all_values = ws.get_all_values()
                if not all_values:
                    return
                max_row = len(all_values)
                max_col = len(all_values[0]) if all_values else 10
                max_row = min(max_row, 500)
                max_col = min(max_col, 20)
                range_str = f"A1:{gspread.utils.rowcol_to_a1(max_row, max_col)}"
            
            sheet_id = ws.id
            
            start_row_num = 1
            end_row_num = 100
            start_col = "A"
            end_col = "Z"
            
            if ":" in range_str:
                start_cell, end_cell = range_str.split(":")
                
                start_row_match = re.search(r'(\d+)$', start_cell)
                end_row_match = re.search(r'(\d+)$', end_cell)
                
                if start_row_match:
                    start_row_num = int(start_row_match.group(1))
                if end_row_match:
                    end_row_num = int(end_row_match.group(1))
                
                if end_row_num < start_row_num:
                    logger.warning(f"Invalid range: endRow {end_row_num} < startRow {start_row_num}, swapping")
                    start_row_num, end_row_num = end_row_num, start_row_num
                
                if end_row_num - start_row_num > 500:
                    end_row_num = start_row_num + 500
                    logger.info(f"Limited formatting range to {end_row_num - start_row_num} rows")
                
                start_col = ''.join(filter(str.isalpha, start_cell)) or "A"
                end_col = ''.join(filter(str.isalpha, end_cell)) or "Z"
            else:
                row_match = re.search(r'(\d+)$', range_str)
                if row_match:
                    start_row_num = int(row_match.group(1))
                    end_row_num = start_row_num
                start_col = ''.join(filter(str.isalpha, range_str)) or "A"
                end_col = start_col
            
            def col_to_index(col_letter):
                index = 0
                for char in col_letter:
                    index = index * 26 + (ord(char.upper()) - ord('A') + 1)
                return index - 1
            
            start_col_idx = col_to_index(start_col)
            end_col_idx = col_to_index(end_col)
            
            requests = [{
                "repeatCell": {
                    "range": {
                        "sheetId": sheet_id,
                        "startRowIndex": start_row_num - 1,
                        "endRowIndex": end_row_num,
                        "startColumnIndex": start_col_idx,
                        "endColumnIndex": end_col_idx + 1
                    },
                    "cell": {
                        "userEnteredFormat": {
                            "textFormat": {
                                "fontFamily": "Calibri",
                                "fontSize": 13,
                                "foregroundColor": {
                                    "red": 0.0,
                                    "green": 0.0,
                                    "blue": 0.0
                                }
                            },
                            "horizontalAlignment": "CENTER",
                            "verticalAlignment": "MIDDLE",
                            "borders": {
                                "top": {"style": "SOLID"},
                                "bottom": {"style": "SOLID"},
                                "left": {"style": "SOLID"},
                                "right": {"style": "SOLID"}
                            }
                        }
                    },
                    "fields": "userEnteredFormat.textFormat,userEnteredFormat.horizontalAlignment,userEnteredFormat.verticalAlignment,userEnteredFormat.borders"
                }
            }]
            
            ws.spreadsheet.batch_update({"requests": requests})
            logger.info(f"Applied formatting to {ws.title} - Range: {range_str}")
            
        except Exception as e:
            logger.warning(f"Formatting failed for {ws.title}: {e}")

    def ensure_status_column(self, department: str, date_str: str) -> None:
        if department != "Sales":
            return
        
        ws = self._get_worksheet(department, date_str)
        try:
            headers = ws.row_values(1)
            if "Report Status" not in headers:
                last_col = len(headers) + 1
                ws.update_cell(1, last_col, "Report Status")
                self._apply_formatting(ws, f"{gspread.utils.rowcol_to_a1(1, last_col)}:{gspread.utils.rowcol_to_a1(1, last_col)}")
                logger.info(f"Added 'Report Status' column to {ws.title}")
        except Exception as e:
            logger.warning(f"Could not ensure status column: {e}")

    def _get_worksheet(self, department: str, date_str: str) -> gspread.Worksheet:
        key = (department, date_str)
        if key in self._ws_cache:
            return self._ws_cache[key]

        ss = self._spreadsheet(department)
        name = self.sheet_name(date_str)
        try:
            ws = ss.worksheet(name)
        except gspread.WorksheetNotFound:
            ws = self._create_worksheet(ss, name, department)

        self._ws_cache[key] = ws
        return ws

    def _create_worksheet(self, ss: gspread.Spreadsheet, name: str, department: str) -> gspread.Worksheet:
        employees = SALES_EMPLOYEES
        headers = SALES_HEADERS
        ws = ss.add_worksheet(title=name, rows=str(len(employees) * 35 + 10), cols="20")
        
        ws.update("A1", [headers])
        ws.update(f"B2:B{len(employees) + 1}", [[emp] for emp in employees])
        self._apply_formatting(ws)
        
        logger.info(f"Created sheet '{name}' for {department}")
        return ws

    def mark_all_as_not_sent(self, department: str, date_str: str) -> None:
        """Mark employees as 'Not Sent' ONLY if they have NO data in other columns"""
        if department != "Sales":
            return
        
        date_key = f"{department}_{date_str}"
        if date_key in self._date_marked_not_sent:
            return
        
        ws = self._get_worksheet(department, date_str)
        
        self.ensure_status_column(department, date_str)
        
        headers = ws.row_values(1)
        status_col = None
        for i, header in enumerate(headers, start=1):
            if header == "Report Status":
                status_col = i
                break
        
        if status_col is None:
            status_col = len(headers) + 1
            ws.update_cell(1, status_col, "Report Status")
            self._apply_formatting(ws, f"{gspread.utils.rowcol_to_a1(1, status_col)}:{gspread.utils.rowcol_to_a1(1, status_col)}")
        
        all_values = self._get_cached_worksheet_data(department, date_str)
        
        updates = []
        ranges_to_format = []
        
        for i, row in enumerate(all_values[1:], start=2):
            row_date = row[0].strip() if len(row) > 0 else ""
            if row_date == date_str:
                has_data = False
                for col_idx, val in enumerate(row[2:], start=3):
                    if val and val.strip() not in ["", "0", "00:00:00"]:
                        has_data = True
                        break
                
                if not has_data:
                    col_letter = gspread.utils.rowcol_to_a1(i, status_col).rstrip("0123456789")
                    range_str = f"{col_letter}{i}"
                    updates.append({"range": range_str, "values": [["Not Sent"]]})
                    ranges_to_format.append(range_str)
        
        if updates:
            for update in updates:
                ws.update(update["range"], update["values"], value_input_option="USER_ENTERED")
            for range_str in ranges_to_format:
                self._apply_formatting(ws, range_str)
            self._date_marked_not_sent.add(date_key)
            self._invalidate_cache(department, date_str)
            logger.info(f"Marked {len(updates)} employees as 'Not Sent' for {date_str}")

    @with_retry()
    def ensure_date_for_all_employees(self, department: str, date_str: str) -> None:
        employees = SALES_EMPLOYEES
        ws = self._get_worksheet(department, date_str)
        
        all_values = self._get_cached_worksheet_data(department, date_str)
        
        has_date = set()
        for row in all_values[1:]:
            if row and row[0].strip() == date_str:
                name = row[1].strip() if len(row) > 1 else ""
                if name:
                    has_date.add(name)
        
        updates = []
        ranges_to_format = []
        for emp in employees:
            if emp not in has_date:
                row_num = len(all_values) + 1 + len(updates)
                range_str = f"A{row_num}:B{row_num}"
                updates.append({"range": range_str, "values": [[date_str, emp]]})
                ranges_to_format.append(range_str)
        
        if updates:
            ws.batch_update(updates, value_input_option="USER_ENTERED")
            for range_str in ranges_to_format:
                self._apply_formatting(ws, range_str)
            self._invalidate_cache(department, date_str)
            logger.info(f"Added date for {len(updates)} employees in {department}")

    @with_retry()
    def find_employee_row(self, department: str, date_str: str, employee_name: str) -> Optional[int]:
        all_values = self._get_cached_worksheet_data(department, date_str)
        for i, row in enumerate(all_values[1:], start=2):
            if row and row[0].strip() == date_str and row[1].strip().lower() == employee_name.lower():
                return i
        return None

    @with_retry()
    def write_batch(self, department: str, date_str: str, updates: List[Tuple[int, Dict]]) -> None:
        if not updates:
            return
        ws = self._get_worksheet(department, date_str)
        mapping = SALES_COLUMN_MAPPING
        
        headers = ws.row_values(1)
        status_col = None
        for i, header in enumerate(headers, start=1):
            if header == "Report Status":
                status_col = i
                break
        
        if status_col is None and department == "Sales":
            status_col = len(headers) + 1
            ws.update_cell(1, status_col, "Report Status")
            self._apply_formatting(ws, f"{gspread.utils.rowcol_to_a1(1, status_col)}:{gspread.utils.rowcol_to_a1(1, status_col)}")
            logger.info(f"Created Report Status column at column {status_col}")
        
        batch_requests = []
        ranges_to_format = []
        
        for row_number, data in updates:
            cell_updates = {}
            
            for field, col in mapping.items():
                if field in ("Date", "Employee Name"):
                    continue
                if field == "Report Status":
                    continue
                val = data.get(field, 0 if field != "Duration" else "00:00:00")
                cell_updates[col] = val
            
            if status_col:
                report_status = data.get("report_status", "")
                cell_updates[status_col] = report_status
                logger.info(f"Setting status for row {row_number} to '{report_status}'")
            
            if not cell_updates:
                continue
            
            cols = sorted(cell_updates)
            min_col, max_col = cols[0], cols[-1]
            row_values = [cell_updates.get(c, "") for c in range(min_col, max_col + 1)]
            col_start = gspread.utils.rowcol_to_a1(row_number, min_col).rstrip("0123456789")
            col_end = gspread.utils.rowcol_to_a1(row_number, max_col).rstrip("0123456789")
            range_str = f"{col_start}{row_number}:{col_end}{row_number}"
            batch_requests.append({"range": range_str, "values": [row_values]})
            ranges_to_format.append(range_str)
        
        if batch_requests:
            ws.batch_update(batch_requests, value_input_option="USER_ENTERED")
            for range_str in ranges_to_format:
                self._apply_formatting(ws, range_str)
            self._invalidate_cache(department, date_str)
            logger.info(f"Batch wrote {len(batch_requests)} rows to {ws.title}")

    def mark_not_sent(self, department: str, date_str: str) -> None:
        if department != "Sales":
            return
        self.mark_all_as_not_sent(department, date_str)

    def mark_invalid_report(self, department: str, date_str: str, employee_name: str) -> None:
        if department != "Sales":
            return
        ws = self._get_worksheet(department, date_str)
        
        headers = ws.row_values(1)
        status_col = None
        for i, header in enumerate(headers, start=1):
            if header == "Report Status":
                status_col = i
                break
        
        if status_col is None:
            status_col = len(headers) + 1
            ws.update_cell(1, status_col, "Report Status")
            self._apply_formatting(ws, f"{gspread.utils.rowcol_to_a1(1, status_col)}:{gspread.utils.rowcol_to_a1(1, status_col)}")
        
        all_values = self._get_cached_worksheet_data(department, date_str)
        row_num = None
        for i, row in enumerate(all_values[1:], start=2):
            row_date = row[0].strip() if len(row) > 0 else ""
            row_name = row[1].strip() if len(row) > 1 else ""
            if row_date == date_str and row_name.lower() == employee_name.lower():
                row_num = i
                break

        if not row_num:
            logger.warning(f"Row not found for {employee_name} on {date_str}")
            return

        col_letter = gspread.utils.rowcol_to_a1(row_num, status_col).rstrip("0123456789")
        range_str = f"{col_letter}{row_num}"
        ws.update(range_str, [["Invalid"]], value_input_option="USER_ENTERED")
        self._apply_formatting(ws, range_str)
        self._invalidate_cache(department, date_str)
        logger.info(f"Marked {employee_name} as 'Invalid' for {date_str}")

    def mark_quota_error(self, department: str, date_str: str, employee_name: str) -> None:
        if department != "Sales":
            return
        ws = self._get_worksheet(department, date_str)
        
        headers = ws.row_values(1)
        status_col = None
        for i, header in enumerate(headers, start=1):
            if header == "Report Status":
                status_col = i
                break
        
        if status_col is None:
            status_col = len(headers) + 1
            ws.update_cell(1, status_col, "Report Status")
            self._apply_formatting(ws, f"{gspread.utils.rowcol_to_a1(1, status_col)}:{gspread.utils.rowcol_to_a1(1, status_col)}")
        
        all_values = self._get_cached_worksheet_data(department, date_str)
        row_num = None
        for i, row in enumerate(all_values[1:], start=2):
            row_date = row[0].strip() if len(row) > 0 else ""
            row_name = row[1].strip() if len(row) > 1 else ""
            if row_date == date_str and row_name.lower() == employee_name.lower():
                row_num = i
                break

        if not row_num:
            logger.warning(f"Row not found for {employee_name} on {date_str}")
            return

        col_letter = gspread.utils.rowcol_to_a1(row_num, status_col).rstrip("0123456789")
        range_str = f"{col_letter}{row_num}"
        ws.update(range_str, [["Quota Error"]], value_input_option="USER_ENTERED")
        self._apply_formatting(ws, range_str)
        self._invalidate_cache(department, date_str)
        logger.info(f"Marked {employee_name} as 'Quota Error' for {date_str}")

    def list_sheets(self, department: str) -> List[str]:
        return [ws.title for ws in self._spreadsheet(department).worksheets()]

    def get_employees_for_date(self, department: str, date_str: str) -> Dict[str, int]:
        all_values = self._get_cached_worksheet_data(department, date_str)
        emp_rows = {}
        for i, row in enumerate(all_values[1:], start=2):
            row_date = row[0].strip() if len(row) > 0 else ""
            row_name = row[1].strip() if len(row) > 1 else ""
            if row_date == date_str and row_name:
                emp_rows[row_name] = i
        return emp_rows
