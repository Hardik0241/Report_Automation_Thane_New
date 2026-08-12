"""
validator.py — Data validation layer.
BRANCH: THANE NEW - Sales Only (No HR)
Handles: employee name (exact + fuzzy), date format, required fields,
         and email-vs-screenshot data comparison with configurable tolerance.
"""

import logging
import re
from difflib import SequenceMatcher
from typing import Dict, List, Optional, Tuple

from config import SALES_EMPLOYEES, VALIDATION_RULES
from utils import parse_duration, validate_date_string

logger = logging.getLogger(__name__)


class DataValidator:

    # ─────────────────────────────────────────
    # Employee name
    # ─────────────────────────────────────────

    def validate_employee_name(
        self, name: str, department: str
    ) -> Tuple[bool, str, str]:
        """
        Returns (is_valid, canonical_name_or_error_msg, reason).

        Steps:
          1. Exact match (case-insensitive stripped).
          2. Partial / substring match.
          3. Fuzzy ratio ≥ threshold.
          4. Fail.
        """
        if not name or not isinstance(name, str):
            return False, "", "Employee name is missing or not a string"

        name_clean = " ".join(name.strip().split()).title()
        employee_list = SALES_EMPLOYEES
        threshold = VALIDATION_RULES.get(department, {}).get("name_fuzzy_threshold", 0.80)

        # 1. Exact
        for emp in employee_list:
            if emp.strip().lower() == name_clean.lower():
                return True, emp, "exact match"

        # 2. Substring (handles "Sachin" matching "Sachin G.")
        matches = [
            emp for emp in employee_list
            if name_clean.lower() in emp.lower() or emp.lower() in name_clean.lower()
        ]
        if len(matches) == 1:
            logger.info(f"Substring match: '{name_clean}' → '{matches[0]}'")
            return True, matches[0], "substring match"

        # 3. Fuzzy
        best_emp, best_ratio = None, 0.0
        for emp in employee_list:
            ratio = SequenceMatcher(None, name_clean.lower(), emp.lower()).ratio()
            if ratio > best_ratio:
                best_ratio, best_emp = ratio, emp

        if best_emp and best_ratio >= threshold:
            logger.warning(
                f"Fuzzy match: '{name_clean}' → '{best_emp}' (score={best_ratio:.2f})"
            )
            return True, best_emp, f"fuzzy match ({best_ratio:.0%})"

        return False, name_clean, (
            f"No employee match for '{name_clean}' in Sales list "
            f"(best: '{best_emp}' @ {best_ratio:.0%})"
        )

    # ─────────────────────────────────────────
    # Date
    # ─────────────────────────────────────────

    def validate_date(self, date_str: str) -> Tuple[bool, Optional[str], str]:
        return validate_date_string(date_str)

    # ─────────────────────────────────────────
    # Required fields
    # ─────────────────────────────────────────

    def validate_required_fields(
        self, data: Dict, department: str
    ) -> Tuple[bool, str]:
        rules = VALIDATION_RULES.get(department, {})
        missing = []

        for field in rules.get("required_fields", []):
            val = data.get(field)
            # Consider 0 as valid (employee may have made 0 calls)
            if val is None or val == "":
                missing.append(field)

        if missing:
            return False, f"Missing required fields: {', '.join(missing)}"
        return True, "All required fields present"

    # ─────────────────────────────────────────
    # Email vs screenshot comparison
    # ─────────────────────────────────────────

    def validate_data_match(
        self,
        email_data: Dict,
        screenshot_data: Optional[Dict],
        department: str,
    ) -> Tuple[bool, str]:
        """
        Compare email-parsed numbers against screenshot-parsed numbers.
        For Sales department: verifies Total Connected and Duration.
        If no screenshot data exists, validation passes (screenshot not required).
        """
        # For Sales, if no screenshot data, skip validation
        if not screenshot_data:
            return True, "No screenshot data - validation skipped"

        return self._validate_sales_data_match(email_data, screenshot_data)

    def _validate_sales_data_match(self, email_data: Dict, screenshot_data: Dict) -> Tuple[bool, str]:
        """Sales-specific validation - compare Total Connected and Duration"""
        mismatches = []

        # 1. Validate Total Connected (email) vs Connected Calls (screenshot)
        email_connected = email_data.get("Total Connected")
        screenshot_connected = screenshot_data.get("Connected Calls")

        if email_connected is None:
            mismatches.append("Total Connected: missing in email")
        elif screenshot_connected is None:
            mismatches.append("Connected Calls: missing in screenshot")
        else:
            email_int = int(email_connected) if str(email_connected).isdigit() else 0
            screenshot_int = int(screenshot_connected) if str(screenshot_connected).isdigit() else 0
            if email_int < screenshot_int:
                mismatches.append(f"Connected Calls invalid: email={email_int} < screenshot={screenshot_int} (should be >=)")

        # 2. Validate Duration (email) vs Total Phone Calls Duration (screenshot)
        email_duration = email_data.get("Duration")
        screenshot_duration = screenshot_data.get("Total Phone Calls Duration")

        if email_duration is None:
            mismatches.append("Duration: missing in email")
        elif screenshot_duration is None:
            mismatches.append("Total Phone Calls Duration: missing in screenshot")
        else:
            e_norm = parse_duration(str(email_duration))
            s_norm = parse_duration(str(screenshot_duration))
            if e_norm < s_norm:
                mismatches.append(f"Duration invalid: email={e_norm} < screenshot={s_norm} (should be >=)")

        if mismatches:
            return False, "Invalid report - " + " | ".join(mismatches)

        return True, "Sales report data verified successfully"

    # ─────────────────────────────────────────
    # Internal
    # ─────────────────────────────────────────

    @staticmethod
    def _within_tolerance(a: int, b: int, pct: int) -> bool:
        if a == b:
            return True
        if b == 0:
            return a == 0
        return abs(a - b) / abs(b) * 100 <= pct
