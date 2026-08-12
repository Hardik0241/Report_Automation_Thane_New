"""
utils.py — Shared utility functions: date extraction, duration parsing, math handling
BRANCH: THANE NEW - Sales Only
UPDATED: Added support for text-based addition patterns (also add, add, plus)
UPDATED: Added dot-separated duration format (HH.MM.SS)
UPDATED: Added support for single-digit seconds format (HH:MM:M) - e.g., 01:28:0
UPDATED: Added support for "sec" as seconds identifier (e.g., 8sec, 42m 8sec)
UPDATED: Added support for single-digit hour with dots (H.MM.SS) - e.g., 2.08.32
UPDATED: Added support for "min" as minutes identifier (e.g., 1hr 25min 46s)
UPDATED: Added support for "MINS" and "SEC" uppercase full words (e.g., 49 MINS 9 SEC)
UPDATED: Fixed duration parsing for addition patterns like "+7 minutes", "+10 min", "also add 10 min"
"""

import re
from datetime import datetime
from typing import Optional, Tuple

from config import DATE_IN_SUBJECT_FORMAT, DATE_PATTERNS, SHEET_NAME_FORMAT


def extract_date_from_subject(subject: str) -> Optional[str]:
    if not subject:
        return None
    for pattern in DATE_PATTERNS:
        match = re.search(pattern, subject)
        if match:
            raw = match.group(1)
            normalized = _normalize_date(raw)
            if normalized:
                return normalized
    return None


def received_timestamp_to_date(timestamp_ms: int) -> str:
    dt = datetime.fromtimestamp(timestamp_ms / 1000)
    return dt.strftime("%d-%m-%Y")


def received_timestamp_to_datetime(timestamp_ms: int) -> datetime:
    return datetime.fromtimestamp(timestamp_ms / 1000)


def _normalize_date(raw: str) -> Optional[str]:
    candidate_formats = [
        "%d-%m-%Y",
        "%d/%m/%Y",
        "%Y-%m-%d",
    ]
    for fmt in candidate_formats:
        try:
            dt = datetime.strptime(raw, fmt)
            return dt.strftime("%d-%m-%Y")
        except ValueError:
            continue
    return None


def date_to_sheet_name(date_str: str) -> str:
    dt = datetime.strptime(date_str, DATE_IN_SUBJECT_FORMAT)
    return dt.strftime(SHEET_NAME_FORMAT)


def validate_date_string(date_str: str) -> Tuple[bool, Optional[str], str]:
    if not date_str:
        return False, None, "Date string is empty"
    normalized = _normalize_date(date_str)
    if normalized:
        return True, normalized, ""
    return False, None, f"Unrecognised date format: {date_str!r}"


def parse_duration(raw: str) -> str:
    """
    Parse duration string to HH:MM:SS format.
    
    Handles:
    - "1h 5m 30s" → 01:05:30
    - "1h 15m + 10 min" → 01:25:00
    - "1h 49m 16s + 12m" → 02:01:16
    - "Duration- 01:28:52" → 01:28:52
    - "01:28:52" → 01:28:52
    - "02.07.36" → 02:07:36
    - "2.08.32" → 02:08:32 (single digit hour with dots)
    - "01:28:0" → 01:28:00 (single digit seconds)
    - "1h 42m 8sec" → 01:42:08 (sec as seconds)
    - "1hr 25min 46s" → 01:25:46 (min as minutes)
    - "49 MINS 9 SEC" → 00:49:09 (uppercase full words)
    - "1H 1M + 20 M, Also add 10 min" → 01:31:00
    """
    if not raw:
        return "00:00:00"
    
    raw = str(raw).strip()
    
    if 'leave' in raw.lower():
        return "00:00:00"
    
    # Handle HH:MM:SS format with colons (exactly 2 digits each)
    match = re.search(r'(\d{2}):(\d{2}):(\d{2})', raw)
    if match:
        return match.group(0)
    
    # Handle HH:MM:M format with single digit seconds (e.g., 01:28:0)
    match = re.search(r'(\d{1,2}):(\d{1,2}):(\d{1})', raw)
    if match:
        h = int(match.group(1))
        m = int(match.group(2))
        s = int(match.group(3))
        return f"{h:02d}:{m:02d}:{s:02d}"
    
    # Handle HH.MM.SS format with dots (two-digit hour)
    match = re.search(r'(\d{2})\.(\d{2})\.(\d{2})', raw)
    if match:
        h, m, s = int(match.group(1)), int(match.group(2)), int(match.group(3))
        return f"{h:02d}:{m:02d}:{s:02d}"
    
    # Handle H.MM.SS format with single digit hour and dots (e.g., 2.08.32)
    match = re.search(r'(\d{1})\.(\d{2})\.(\d{2})', raw)
    if match:
        h = int(match.group(1))
        m = int(match.group(2))
        s = int(match.group(3))
        return f"{h:02d}:{m:02d}:{s:02d}"
    
    # Handle HH:MM:SS format with single digit hour/minute (e.g., 1:28:30)
    match = re.search(r'(\d{1,2}):(\d{1,2}):(\d{1,2})', raw)
    if match:
        h = int(match.group(1))
        m = int(match.group(2))
        s = int(match.group(3))
        return f"{h:02d}:{m:02d}:{s:02d}"
    
    # Handle MM:SS format
    match = re.search(r'(\d{2}):(\d{2})', raw)
    if match and ':' in raw and raw.count(':') == 1:
        m, s = int(match.group(1)), int(match.group(2))
        return f"00:{m:02d}:{s:02d}"
    
    # Handle multiple durations with "+" and text additions
    if '+' in raw or re.search(r'(also add|add|plus|additional)', raw, re.IGNORECASE):
        total_seconds = 0
        
        # Split by common separators
        parts = re.split(r'[\+]|also add|add|plus|additional', raw, flags=re.IGNORECASE)
        for part in parts:
            if part.strip():
                total_seconds += _duration_to_seconds(part.strip())
        return _seconds_to_hms(total_seconds)
    
    seconds = _duration_to_seconds(raw)
    return _seconds_to_hms(seconds)


def _duration_to_seconds(duration_str: str) -> int:
    duration_str = duration_str.strip().lower()
    total_seconds = 0
    
    # Remove any text in parentheses or after keywords
    duration_str = re.sub(r'\s+(?:on|from|another|whatsapp|other|phone|personal|prsnl).*$', '', duration_str, flags=re.IGNORECASE)
    
    # Handle addition patterns with + symbol
    addition_match = re.search(r'\+\s*(\d+)\s*(?:min(?:ute)?s?)', duration_str, re.IGNORECASE)
    if addition_match:
        extra_minutes = int(addition_match.group(1))
        total_seconds += extra_minutes * 60
        duration_str = re.sub(r'\+\s*\d+\s*(?:min(?:ute)?s?)', '', duration_str, flags=re.IGNORECASE)
    
    addition_match = re.search(r'\+\s*(\d+)\s*m', duration_str, re.IGNORECASE)
    if addition_match:
        extra_minutes = int(addition_match.group(1))
        total_seconds += extra_minutes * 60
        duration_str = re.sub(r'\+\s*\d+\s*m', '', duration_str, flags=re.IGNORECASE)
    
    addition_match = re.search(r'\+\s*(\d+)\s*s', duration_str, re.IGNORECASE)
    if addition_match:
        extra_seconds = int(addition_match.group(1))
        total_seconds += extra_seconds
        duration_str = re.sub(r'\+\s*\d+\s*s', '', duration_str, flags=re.IGNORECASE)
    
    # Handle text-based addition patterns (also add X min, add X minutes, plus X min)
    text_addition = re.search(r'(?:also add|add|plus|additional)\s+(\d+)\s*(?:min(?:ute)?s?)', duration_str, re.IGNORECASE)
    if text_addition:
        extra_minutes = int(text_addition.group(1))
        total_seconds += extra_minutes * 60
        duration_str = re.sub(r'(?:also add|add|plus|additional)\s+\d+\s*(?:min(?:ute)?s?)', '', duration_str, flags=re.IGNORECASE)
    
    # Handle HH.MM.SS format with dots (two-digit hour)
    match = re.search(r'(\d{2})\.(\d{2})\.(\d{2})', duration_str)
    if match:
        h, m, s = int(match.group(1)), int(match.group(2)), int(match.group(3))
        total_seconds += h * 3600 + m * 60 + s
        return total_seconds
    
    # Handle H.MM.SS format with single digit hour and dots (e.g., 2.08.32)
    match = re.search(r'(\d{1})\.(\d{2})\.(\d{2})', duration_str)
    if match:
        h = int(match.group(1))
        m = int(match.group(2))
        s = int(match.group(3))
        total_seconds += h * 3600 + m * 60 + s
        return total_seconds
    
    # Handle HH:MM:M format with single digit seconds (e.g., 01:28:0)
    match = re.search(r'(\d{1,2}):(\d{1,2}):(\d{1})', duration_str)
    if match:
        h = int(match.group(1))
        m = int(match.group(2))
        s = int(match.group(3))
        total_seconds += h * 3600 + m * 60 + s
        return total_seconds
    
    # NEW: Handle "49 MINS 9 SEC" format (uppercase full words)
    # Pattern for "X MINS Y SEC"
    match = re.search(r'(\d+)\s*MINS?\s*(\d+)\s*SEC', duration_str, re.IGNORECASE)
    if match:
        m, s = int(match.group(1)), int(match.group(2))
        total_seconds += m * 60 + s
        return total_seconds
    
    # Pattern for "X MINS" only (no seconds)
    match = re.search(r'(\d+)\s*MINS?', duration_str, re.IGNORECASE)
    if match:
        total_seconds += int(match.group(1)) * 60
        return total_seconds
    
    # Pattern for "X SEC" only (no minutes)
    match = re.search(r'(\d+)\s*SEC', duration_str, re.IGNORECASE)
    if match:
        total_seconds += int(match.group(1))
        return total_seconds
    
    # Handle duration with "sec" as seconds identifier (e.g., 1h 42m 8sec)
    # Pattern for "Xh Ym Zsec"
    match = re.search(r'(\d+)\s*h(?:r)?s?\s*(\d+)\s*m(?:in)?s?\s*(\d+)\s*sec', duration_str, re.IGNORECASE)
    if match:
        h, m, s = int(match.group(1)), int(match.group(2)), int(match.group(3))
        total_seconds += h * 3600 + m * 60 + s
        return total_seconds
    
    # NEW: Handle duration with "min" as minutes identifier (e.g., 1hr 25min 46s)
    # Pattern for "Xhr Ymin Zs"
    match = re.search(r'(\d+)\s*hr\s*(\d+)\s*min\s*(\d+)\s*s', duration_str, re.IGNORECASE)
    if match:
        h, m, s = int(match.group(1)), int(match.group(2)), int(match.group(3))
        total_seconds += h * 3600 + m * 60 + s
        return total_seconds
    
    # Pattern for "Ymin Zs" (no hours)
    match = re.search(r'(\d+)\s*min\s*(\d+)\s*s', duration_str, re.IGNORECASE)
    if match:
        m, s = int(match.group(1)), int(match.group(2))
        total_seconds += m * 60 + s
        return total_seconds
    
    # Pattern for just "Zmin" (only minutes)
    match = re.search(r'(\d+)\s*min', duration_str, re.IGNORECASE)
    if match:
        total_seconds += int(match.group(1)) * 60
        return total_seconds
    
    # Pattern for "Ym Zsec" (no hours)
    match = re.search(r'(\d+)\s*m(?:in)?s?\s*(\d+)\s*sec', duration_str, re.IGNORECASE)
    if match:
        m, s = int(match.group(1)), int(match.group(2))
        total_seconds += m * 60 + s
        return total_seconds
    
    # Pattern for just "Zsec" (only seconds)
    match = re.search(r'(\d+)\s*sec', duration_str, re.IGNORECASE)
    if match:
        total_seconds += int(match.group(1))
        return total_seconds
    
    # Parse main duration - text formats (standard s for seconds)
    match = re.search(r'(\d+)\s*h(?:r)?s?\s*(\d+)\s*m(?:in)?s?\s*(\d+)\s*s(?:ec)?s?', duration_str, re.IGNORECASE)
    if match:
        h, m, s = int(match.group(1)), int(match.group(2)), int(match.group(3))
        total_seconds += h * 3600 + m * 60 + s
        return total_seconds
    
    match = re.search(r'(\d+)\s*h(?:r)?s?\s*(\d+)\s*m(?:in)?s?', duration_str, re.IGNORECASE)
    if match:
        h, m = int(match.group(1)), int(match.group(2))
        total_seconds += h * 3600 + m * 60
        return total_seconds
    
    match = re.search(r'(\d+)\s*[hH]\s*(\d+)\s*[mM]', duration_str)
    if match:
        h, m = int(match.group(1)), int(match.group(2))
        total_seconds += h * 3600 + m * 60
        return total_seconds
    
    match = re.search(r'(\d+)\s*h(?:r)?s?', duration_str, re.IGNORECASE)
    if match:
        total_seconds += int(match.group(1)) * 3600
        return total_seconds
    
    match = re.search(r'(\d+)\s*m(?:in)?s?\s*(\d+)\s*s(?:ec)?s?', duration_str, re.IGNORECASE)
    if match:
        m, s = int(match.group(1)), int(match.group(2))
        total_seconds += m * 60 + s
        return total_seconds
    
    match = re.search(r'(\d+)\s*m(?:in)?s?', duration_str, re.IGNORECASE)
    if match:
        total_seconds += int(match.group(1)) * 60
        return total_seconds
    
    match = re.search(r'(\d+)\s*s(?:ec)?s?', duration_str, re.IGNORECASE)
    if match:
        total_seconds += int(match.group(1))
        return total_seconds
    
    # Handle HH:MM:SS format with colons
    match = re.search(r'(\d{2}):(\d{2}):(\d{2})', duration_str)
    if match:
        h, m, s = int(match.group(1)), int(match.group(2)), int(match.group(3))
        total_seconds += h * 3600 + m * 60 + s
        return total_seconds
    
    # Handle HH:MM format with colons
    match = re.search(r'(\d{2}):(\d{2})', duration_str)
    if match:
        h, m = int(match.group(1)), int(match.group(2))
        total_seconds += h * 3600 + m * 60
        return total_seconds
    
    # Handle MM:SS format
    match = re.search(r'(\d{2}):(\d{2})', duration_str)
    if match:
        m, s = int(match.group(1)), int(match.group(2))
        total_seconds += m * 60 + s
        return total_seconds
    
    return total_seconds


def _seconds_to_hms(total_seconds: int) -> str:
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    seconds = total_seconds % 60
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


def duration_to_seconds(raw: str) -> int:
    return _duration_to_seconds(raw)


def seconds_to_hms(seconds: int) -> str:
    return _seconds_to_hms(seconds)


def coerce_int(value) -> int:
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    
    str_val = str(value).strip()
    
    if str_val.lower() == 'leave':
        return 0
    
    if '+' in str_val:
        parts = re.split(r'\s*\+\s*', str_val)
        total = 0
        for part in parts:
            nums = re.findall(r'\d+', part)
            if nums:
                total += int(nums[0])
        return total
    
    nums = re.findall(r"\d+", str_val)
    return int(nums[0]) if nums else 0


def safe_title(name: str) -> str:
    if not name:
        return ""
    return " ".join(name.strip().split()).title()


def normalize_employee_name(name: str) -> str:
    if not name:
        return ""
    words = name.strip().split()
    filtered = []
    for word in words:
        clean = word.rstrip(".")
        if len(clean) == 1 and clean.isalpha():
            continue
        filtered.append(word)
    return safe_title(" ".join(filtered))


def extract_email_address(from_header: str) -> str:
    match = re.search(r'<([^>]+)>', from_header)
    if match:
        return match.group(1).strip().lower()
    match = re.search(r'[\w.+-]+@[\w.-]+\.\w+', from_header)
    if match:
        return match.group(0).strip().lower()
    return from_header.strip().lower()
