"""
gemini_parser.py — Parse email body into structured data using Gemini.
BRANCH: THANE NEW - Sales Only (No HR)
UPDATED: Removed all HR-related code
UPDATED: Fixed duration extraction for HH:MM:SS format with dash and dots
UPDATED: Added support for "sec" as seconds identifier (e.g., 8sec, 42m 8sec)
UPDATED: Added support for "total dialled" (double L) spelling variation
UPDATED: Added support for "Connect" without "ed" (e.g., Connect:- 74)
UPDATED: Added support for "1hr" format (e.g., 1hr 14m 21s)
UPDATED: Added support for "min" as minutes identifier (e.g., 1hr 25min 46s)
UPDATED: Added support for "MINS" and "SEC" uppercase full words (e.g., 49 MINS 9 SEC)
UPDATED: Added support for "hr" and "min" and "sec" full words (e.g., 1hr 9min 47sec)
UPDATED: Added support for MM:SS format (e.g., 58:14)
UPDATED: Added "Connect" with capital C to keywords list for better matching
UPDATED: Improved call number extraction precision
"""

import json
import logging
import re
from typing import Dict, Optional

import warnings
warnings.filterwarnings('ignore', category=FutureWarning)
import google.generativeai as genai

from config import GEMINI_API_KEY, GEMINI_MODEL, SALES_EMAIL_MAP
from error_handler import with_retry
from utils import coerce_int, normalize_employee_name, parse_duration, safe_title

logger = logging.getLogger(__name__)

genai.configure(api_key=GEMINI_API_KEY)

_BASE_PROMPT = """
You are a data extraction assistant. Extract information from this daily work-report email.

Return ONLY a JSON object — no markdown, no explanation.

IMPORTANT: This is a SALES report only.

For a SALES report, look for:
- "total dialed", "total dial", "total dialled", "dials", "total calls", "calls made", "dial"
- "connected", "conn", "total connected", "connected calls", "connect"  
- "duration", "dur", "talk time", "time"
- "prospect", "prospects", "pros"
- BDE name patterns: "BDE Name:", "BDE -", "BDE:"

For SALES report:
{
  "employee_name": "string or empty",
  "department": "Sales",
  "Total Dialed": integer,
  "Total Connected": integer,
  "Duration": "HH:MM:SS",
  "Prospect": integer
}

Rules:
- Use 0 for missing integer fields.
- Use "00:00:00" for missing duration.
- If the email contains "Leave" or "leave" anywhere, mark as "Leave" and skip.
- Duration can be in formats: "1h 0m 35s", "1H 15M + 14M", "1 H 31 M", "1hr 25m 21s", "01:28:52", "02.07.36", "2.08.32", "1h 42m 8sec", "1hr 14m 21s", "1hr 25min 46s", "49 MINS 9 SEC", "1hr 9min 47sec", "58:14"

Email content:
"""


class GeminiParser:
    def __init__(self):
        self.model = genai.GenerativeModel(GEMINI_MODEL)

    @with_retry()
    def parse_email(self, body: str, sender_email: str = "") -> Optional[Dict]:
        if not body or not body.strip():
            logger.warning("Empty email body — skipping Gemini call.")
            return None

        prompt = _BASE_PROMPT + body[:5000]

        data = None
        try:
            response = self.model.generate_content(prompt)
            raw_text = response.text.strip()
            data = self._extract_json(raw_text)
        except Exception as exc:
            if "429" in str(exc) or "quota" in str(exc).lower():
                logger.warning(f"⚠️ Gemini API quota exceeded - using regex fallback parser")
            else:
                logger.warning(f"Gemini call failed ({exc}); trying regex fallback.")
            data = None

        if data is None:
            logger.info("Using regex fallback parser.")
            data = self._fallback_parse(body)

        if data is None:
            return None

        return self._clean(data, body, sender_email)

    @staticmethod
    def _extract_json(text: str) -> Optional[Dict]:
        text = re.sub(r"```(?:json)?", "", text).strip()
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            return None
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            return None

    def _clean(self, data: Dict, original_body: str, sender_email: str = "") -> Dict:
        dept = data.get("department", "Sales")
        if dept != "Sales":
            dept = "Sales"
        data["department"] = dept

        raw_name = data.get("employee_name", "") or ""
        data["employee_name"] = normalize_employee_name(raw_name)

        # Sales only - no HR
        for field in ["Total Dialed", "Total Connected", "Prospect"]:
            data[field] = coerce_int(data.get(field, 0))
        data["Duration"] = parse_duration(data.get("Duration", ""))

        # Remove any HR fields if present
        for k in ["Total Calls", "Connected Calls", "Tomorrow Interview Lineups", "Interview Held"]:
            data.pop(k, None)

        return data

    @staticmethod
    def _detect_department(text: str, sender_email: str = "") -> str:
        # Always return Sales for branch repos
        return "Sales"

    def _fallback_parse(self, text: str) -> Optional[Dict]:
        if 'leave' in text.lower():
            return {
                "employee_name": self._extract_name(text),
                "department": "Sales",
                "Total Dialed": 0,
                "Total Connected": 0,
                "Duration": "00:00:00",
                "Prospect": 0,
            }

        dept = "Sales"
        dur = self._extract_duration_flexible(text)
        name = self._extract_name(text)

        def grab_number(keywords: list) -> int:
            for kw in keywords:
                kw_esc = re.escape(kw)
                patterns = [
                    rf"(?i){kw_esc}[\s]*[:=-][\s]*(\d+(?:\s*\+\s*\d+)*)",
                    rf"(?i){kw_esc}[\s]*:[\s]*(\d+(?:\s*\+\s*\d+)*)",
                    rf"(?i){kw_esc}[\s]*-[\s]*(\d+(?:\s*\+\s*\d+)*)",
                    rf"(?i){kw_esc}\s+(\d+(?:\s*\+\s*\d+)*)",
                    rf"(?i){kw_esc}:(\d+(?:\s*\+\s*\d+)*)",
                    rf"(?i){kw_esc}-(\d+(?:\s*\+\s*\d+)*)",
                    rf"(?i){kw_esc}:-(\d+(?:\s*\+\s*\d+)*)",
                ]
                for pattern in patterns:
                    match = re.search(pattern, text)
                    if match:
                        value_str = match.group(1)
                        if '+' in value_str:
                            parts = re.split(r'\s*\+\s*', value_str)
                            total = 0
                            for part in parts:
                                nums = re.findall(r'\d+', part)
                                if nums:
                                    total += int(nums[0])
                            return total
                        nums = re.findall(r'\d+', value_str)
                        if nums:
                            return int(nums[0])
            return 0

        def grab_duration(keywords: list) -> str:
            for kw in keywords:
                kw_esc = re.escape(kw)

                pattern_time = rf"(?i){kw_esc}[\s]*[:=-][\s]*(\d{{2}}:\d{{2}}:\d{{2}})"
                match = re.search(pattern_time, text)
                if match:
                    return match.group(1)

                pattern_dots_two = rf"(?i){kw_esc}[\s]*[:=-][\s]*(\d{{2}}\.\d{{2}}\.\d{{2}})"
                match = re.search(pattern_dots_two, text)
                if match:
                    return match.group(1).replace('.', ':')

                pattern_dots_one = rf"(?i){kw_esc}[\s]*[:=-][\s]*(\d{{1}}\.\d{{2}}\.\d{{2}})"
                match = re.search(pattern_dots_one, text)
                if match:
                    return match.group(1).replace('.', ':')

                pattern_time_colon = rf"(?i){kw_esc}[\s]*:[\s]*(\d{{2}}:\d{{2}}:\d{{2}})"
                match = re.search(pattern_time_colon, text)
                if match:
                    return match.group(1)

                # Handle MM:SS format (e.g., 58:14)
                pattern_mm_ss = rf"(?i){kw_esc}[\s]*[:=-][\s]*(\d{{2}}:\d{{2}})"
                match = re.search(pattern_mm_ss, text)
                if match:
                    return match.group(1).strip()

                # Handle text format with "sec" (e.g., 1h 42m 8sec)
                pattern_text_sec = rf"(?i){kw_esc}[\s]*[:=-][\s]*(\d+\s*h(?:r)?s?\s*\d+\s*m(?:in)?s?\s*\d+\s*sec)"
                match = re.search(pattern_text_sec, text)
                if match:
                    return match.group(1).strip()

                # Handle text format with "hr" and "min" (e.g., 1hr 25min 46s)
                pattern_text_hr_min = rf"(?i){kw_esc}[\s]*[:=-][\s]*(\d+\s*hr\s*\d+\s*min\s*\d+\s*s)"
                match = re.search(pattern_text_hr_min, text)
                if match:
                    return match.group(1).strip()

                # Handle "1hr 9min 47sec" format (full words with spaces)
                pattern_hr_min_sec = rf"(?i){kw_esc}[\s]*[:=-][\s]*(\d+\s*hr\s*\d+\s*min\s*\d+\s*sec)"
                match = re.search(pattern_hr_min_sec, text)
                if match:
                    return match.group(1).strip()

                # Handle "49 MINS 9 SEC" format (uppercase full words)
                pattern_mins_sec = rf"(?i){kw_esc}[\s]*[:=-][\s]*(\d+\s*MINS?\s*\d+\s*SEC)"
                match = re.search(pattern_mins_sec, text)
                if match:
                    return match.group(1).strip()

                # Handle text format with "hr" (e.g., 1hr 14m 21s)
                pattern_text_hr = rf"(?i){kw_esc}[\s]*[:=-][\s]*(\d+\s*hr\s*\d+\s*m\s*\d+\s*s)"
                match = re.search(pattern_text_hr, text)
                if match:
                    return match.group(1).strip()

                pattern_text = rf"(?i){kw_esc}[\s]*[:=-][\s]*([\d\s]+[hms]+[\d\s]+[hms]*[\d\s]*[hms]*)"
                match = re.search(pattern_text, text)
                if match:
                    return match.group(1).strip()

                pattern_text_space = rf"(?i){kw_esc}\s+([\d\s]+[hms]+[\d\s]+[hms]*[\d\s]*[hms]*)"
                match = re.search(pattern_text_space, text)
                if match:
                    return match.group(1).strip()

            return "00:00:00"

        # Sales only - no HR
        total_dialed = grab_number([
            "total dial", "total dials", "total dialed", "total dialled",
            "total calls", "calls made", "dials", "dial"
        ])

        total_connected = grab_number([
            "total connected", "connected calls", "connected",
            "conn", "connect", "Connect"
        ])

        prospect = grab_number([
            "prospect", "prospects", "pros"
        ])

        duration = grab_duration([
            "duration", "dur", "talk time", "time"
        ])
        if duration and duration != "00:00:00" and ':' not in duration and '.' not in duration:
            duration = parse_duration(duration)

        return {
            "employee_name": name,
            "department": "Sales",
            "Total Dialed": total_dialed,
            "Total Connected": total_connected,
            "Duration": duration,
            "Prospect": prospect,
        }

    @staticmethod
    def _extract_name(text: str) -> str:
        bde_patterns = [
            r'BDE[:\s-]+\s*([A-Za-z]+(?:\s+[A-Za-z]+)?)',
            r'BDE Name[:\s-]+\s*([A-Za-z]+(?:\s+[A-Za-z]+)?)',
            r'BDE NAME[:\s-]+\s*([A-Za-z]+(?:\s+[A-Za-z]+)?)',
            r'Name[:\s-]+\s*([A-Za-z]+(?:\s+[A-Za-z]+)?)',
        ]
        for pattern in bde_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(1).strip()

        ignore_words = [
            'dear', 'hi', 'hello', 'kindly', 'please', 'thanks', 'thank',
            'regards', 'sincerely', 'best', 'warm', 'good', 'morning',
            'afternoon', 'evening', 'hardik', 'sir', 'madam', 'team',
            'everyone', 'all', 'daily', 'report', 'calling', 'kra',
            'subject', 'forwarded', 'attachment', 'see', 'below',
            'attached', 'please find', 'here is', 'today\'s', 'sales',
            'hr', 'dialer', 'total', 'connected', 'duration',
            'kindly check', 'bde', 'prospect', 'kfb', 'dear sir', 'bde -',
            'calling', 'prospect', 'edujam', 'gmail', 'com'
        ]

        for line in text.splitlines():
            line = line.strip()
            if len(line) < 3:
                continue
            if re.search(r'\d', line):
                continue
            if re.search(r'[:=\-@.]', line):
                continue
            if len(line) > 50:
                continue
            line_lower = line.lower()
            if any(word in line_lower for word in ignore_words):
                continue
            line = re.sub(r'^(bde\s*-\s*)', '', line, flags=re.IGNORECASE)
            line = re.sub(r'^(dear\s+sir\s*-\s*)', '', line, flags=re.IGNORECASE)
            if line.strip():
                return line

        return ""

    @staticmethod
    def _extract_duration_flexible(text: str) -> str:
        if 'leave' in text.lower():
            return "00:00:00"

        match = re.search(r'(\d{2}):(\d{2}):(\d{2})', text)
        if match:
            return match.group(0)

        # Handle MM:SS format (e.g., 58:14)
        match = re.search(r'(\d{2}):(\d{2})', text)
        if match and text.count(':') == 1:
            m, s = int(match.group(1)), int(match.group(2))
            return f"00:{m:02d}:{s:02d}"

        # Handle HH.MM.SS with two-digit hour
        match = re.search(r'(\d{2})\.(\d{2})\.(\d{2})', text)
        if match:
            h, m, s = int(match.group(1)), int(match.group(2)), int(match.group(3))
            return f"{h:02d}:{m:02d}:{s:02d}"

        # Handle H.MM.SS with single-digit hour (e.g., 2.08.32)
        match = re.search(r'(\d{1})\.(\d{2})\.(\d{2})', text)
        if match:
            h = int(match.group(1))
            m = int(match.group(2))
            s = int(match.group(3))
            return f"{h:02d}:{m:02d}:{s:02d}"

        # Handle "49 MINS 9 SEC" format (uppercase full words)
        match = re.search(r'(\d+)\s*MINS?\s*(\d+)\s*SEC', text, re.IGNORECASE)
        if match:
            m, s = int(match.group(1)), int(match.group(2))
            return f"00:{m:02d}:{s:02d}"

        # Handle "1hr 9min 47sec" format (full words with spaces)
        match = re.search(r'(\d+)\s*hr\s*(\d+)\s*min\s*(\d+)\s*sec', text, re.IGNORECASE)
        if match:
            h, m, s = int(match.group(1)), int(match.group(2)), int(match.group(3))
            return f"{h:02d}:{m:02d}:{s:02d}"

        # Handle "1hr 25min 46s" format
        match = re.search(r'(\d+)\s*hr\s*(\d+)\s*min\s*(\d+)\s*s', text, re.IGNORECASE)
        if match:
            h, m, s = int(match.group(1)), int(match.group(2)), int(match.group(3))
            return f"{h:02d}:{m:02d}:{s:02d}"

        # Handle "1hr 14m 21s" format
        match = re.search(r'(\d+)\s*hr\s*(\d+)\s*m\s*(\d+)\s*s', text, re.IGNORECASE)
        if match:
            h, m, s = int(match.group(1)), int(match.group(2)), int(match.group(3))
            return f"{h:02d}:{m:02d}:{s:02d}"

        # Handle "1h 42m 8sec" format
        match = re.search(r'(\d+)\s*h(?:r)?\s*(\d+)\s*m\s*(\d+)\s*sec', text, re.IGNORECASE)
        if match:
            h, m, s = int(match.group(1)), int(match.group(2)), int(match.group(3))
            return f"{h:02d}:{m:02d}:{s:02d}"

        match = re.search(r'(\d+)\s*h(?:r)?\s*(\d+)\s*m\s*(\d+)\s*s', text, re.IGNORECASE)
        if match:
            h, m, s = int(match.group(1)), int(match.group(2)), int(match.group(3))
            return f"{h:02d}:{m:02d}:{s:02d}"

        match = re.search(r'(\d+)\s*h(?:r)?\s*(\d+)\s*m', text, re.IGNORECASE)
        if match:
            h, m = int(match.group(1)), int(match.group(2))
            return f"{h:02d}:{m:02d}:00"

        match = re.search(r'(\d+)\s*m\s*(\d+)\s*s', text, re.IGNORECASE)
        if match:
            m, s = int(match.group(1)), int(match.group(2))
            return f"00:{m:02d}:{s:02d}"

        match = re.search(r'(\d+)\s*m', text, re.IGNORECASE)
        if match:
            m = int(match.group(1))
            return f"00:{m:02d}:00"

        return "00:00:00"
