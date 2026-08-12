"""
tracker.py — Email processing tracker with proper logging and duplicate detection
BRANCH: THANE NEW - Sales Only
Prevents processing same email multiple times
UPDATED: Enhanced duplicate detection to prevent multiple SUCCESS/FAILED entries for same employee/date
"""

import csv
import json
import logging
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Set, Tuple

from config import (
    DUPLICATE_CACHE_PATH,
    DUPLICATE_WINDOW_HOURS,
    LOG_DIR,
    PROCESSING_LOG_PATH,
)

logger = logging.getLogger(__name__)

_CSV_COLUMNS = [
    "Timestamp", "Email_ID", "Email_Subject", "Sender_Email",
    "Sender_Name", "Received_Time", "Status", "Department",
    "Employee_Name", "Date", "Reason", "Processing_Time_Sec",
]


class Tracker:
    def __init__(self):
        for path in [LOG_DIR, "logs", "Working_Report_Editor/logs"]:
            try:
                os.makedirs(path, exist_ok=True)
                logger.info(f"Created/verified logs directory: {path}")
            except Exception as e:
                logger.warning(f"Could not create {path}: {e}")
        
        self.log_path = PROCESSING_LOG_PATH
        if not os.path.exists(LOG_DIR):
            self.log_path = "logs/processing_logs.csv"
        
        self._init_csv()
        self._init_cache()

    def _init_csv(self):
        try:
            os.makedirs(os.path.dirname(self.log_path), exist_ok=True)
            if not os.path.exists(self.log_path):
                with open(self.log_path, "w", newline="", encoding="utf-8") as fh:
                    csv.writer(fh).writerow(_CSV_COLUMNS)
                logger.info(f"Created new log file at: {self.log_path}")
        except Exception as exc:
            logger.error(f"Failed to init CSV: {exc}")

    def _init_cache(self):
        try:
            cache_dir = os.path.dirname(DUPLICATE_CACHE_PATH)
            if cache_dir:
                os.makedirs(cache_dir, exist_ok=True)
            if not os.path.exists(DUPLICATE_CACHE_PATH):
                with open(DUPLICATE_CACHE_PATH, "w") as fh:
                    json.dump({}, fh)
                logger.info(f"Created cache file at: {DUPLICATE_CACHE_PATH}")
        except Exception as exc:
            logger.error(f"Failed to init cache: {exc}")

    def _load_cache(self) -> Dict:
        try:
            with open(DUPLICATE_CACHE_PATH, "r") as fh:
                return json.load(fh)
        except Exception:
            return {}

    def _save_cache(self, cache: Dict) -> None:
        try:
            with open(DUPLICATE_CACHE_PATH, "w") as fh:
                json.dump(cache, fh, indent=2)
        except Exception as exc:
            logger.error(f"Could not save duplicate cache: {exc}")

    def is_duplicate(self, email_hash: str) -> bool:
        if not email_hash:
            return False
        cache = self._load_cache()
        last_str = cache.get(email_hash)
        if not last_str:
            return False
        last_dt = datetime.fromisoformat(last_str)
        return datetime.now() - last_dt < timedelta(hours=DUPLICATE_WINDOW_HOURS)

    def mark_processed(self, email_hash: str) -> None:
        if not email_hash:
            return
        cache = self._load_cache()
        cache[email_hash] = datetime.now().isoformat()
        cutoff = datetime.now() - timedelta(hours=DUPLICATE_WINDOW_HOURS * 2)
        cache = {k: v for k, v in cache.items() if datetime.fromisoformat(v) > cutoff}
        self._save_cache(cache)
        logger.info(f"Marked email {email_hash[:16]}... as processed")

    def is_processed(self, email_hash: str) -> bool:
        return self.is_duplicate(email_hash)
    
    def has_success_for_employee(self, department: str, employee_name: str, date: str) -> bool:
        try:
            with open(self.log_path, "r", encoding="utf-8") as fh:
                reader = csv.DictReader(fh)
                for row in reader:
                    if (row.get("Status") == "SUCCESS" and 
                        row.get("Department") == department and 
                        row.get("Employee_Name") == employee_name and 
                        row.get("Date") == date):
                        return True
        except Exception:
            pass
        return False
    
    def has_failed_for_employee(self, department: str, employee_name: str, date: str) -> bool:
        try:
            with open(self.log_path, "r", encoding="utf-8") as fh:
                reader = csv.DictReader(fh)
                for row in reader:
                    if (row.get("Status") == "FAILED" and 
                        row.get("Department") == department and 
                        row.get("Employee_Name") == employee_name and 
                        row.get("Date") == date):
                        return True
        except Exception:
            pass
        return False

    def log_status(self, email_preview: str, status: str, email_id: str = "",
                   department: str = "", employee_name: str = "", date: str = "",
                   reason: str = "", processing_time: float = 0.0,
                   sender_email: str = "", sender_name: str = "",
                   received_time: Optional[datetime] = None) -> None:
        
        if self.has_success_for_employee(department, employee_name, date):
            logger.info(f"⏭️ Skipping {status} log for {employee_name} on {date} - SUCCESS already recorded")
            return
        
        if status == "FAILED":
            if self.has_failed_for_employee(department, employee_name, date):
                logger.info(f"⏭️ Skipping duplicate FAILED log for {employee_name} on {date} - already logged")
                return
        
        received_iso = received_time.isoformat() if received_time else ""
        row = [
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            email_id,
            (email_preview or "")[:200],
            sender_email,
            sender_name,
            received_iso,
            status,
            department,
            employee_name,
            date,
            (reason or "")[:300],
            f"{processing_time:.2f}",
        ]
        try:
            os.makedirs(os.path.dirname(self.log_path), exist_ok=True)
            with open(self.log_path, "a", newline="", encoding="utf-8") as fh:
                csv.writer(fh).writerow(row)
            logger.info(f"Logged {status} for {employee_name or email_preview[:20]}")
        except Exception as exc:
            logger.error(f"Failed to write log: {exc}")

    def get_statistics(self) -> Dict:
        try:
            with open(self.log_path, "r", encoding="utf-8") as fh:
                rows = list(csv.DictReader(fh))
        except Exception:
            rows = []
        
        unique_successes = set()
        unique_failures = set()
        
        for r in rows:
            if r.get("Status") == "SUCCESS":
                key = (r.get("Department", ""), r.get("Employee_Name", ""), r.get("Date", ""))
                unique_successes.add(key)
            elif r.get("Status") == "FAILED":
                key = (r.get("Department", ""), r.get("Employee_Name", ""), r.get("Date", ""))
                unique_failures.add(key)
        
        total = len(unique_successes) + len(unique_failures)
        success = len(unique_successes)
        failed = len(unique_failures)
        
        return {
            "total": total,
            "success": success,
            "failed": failed,
            "rate": round(success / total * 100, 1) if total > 0 else 0,
            "today_success": success,
        }

    def get_failed_rows(self) -> List[Dict]:
        try:
            with open(self.log_path, "r", encoding="utf-8") as fh:
                rows = list(csv.DictReader(fh))
                seen = set()
                unique_failures = []
                for r in rows:
                    if r.get("Status") == "FAILED":
                        key = (r.get("Department", ""), r.get("Employee_Name", ""), r.get("Date", ""))
                        if key not in seen:
                            seen.add(key)
                            unique_failures.append(r)
                return unique_failures
        except Exception:
            return []
    
    def get_recent_activity(self, limit: int = 15) -> List[Dict]:
        try:
            with open(self.log_path, "r", encoding="utf-8") as fh:
                rows = list(csv.DictReader(fh))
            
            latest_per_employee: Dict[Tuple[str, str, str], Dict] = {}
            
            for row in rows:
                key = (row.get("Department", ""), row.get("Employee_Name", ""), row.get("Date", ""))
                if key not in latest_per_employee:
                    latest_per_employee[key] = row
                else:
                    existing_status = latest_per_employee[key].get("Status")
                    new_status = row.get("Status")
                    if existing_status == "FAILED" and new_status == "SUCCESS":
                        latest_per_employee[key] = row
            
            unique_rows = list(latest_per_employee.values())
            unique_rows.sort(key=lambda x: x.get("Timestamp", ""), reverse=True)
            
            return unique_rows[:limit]
        except Exception:
            return []
