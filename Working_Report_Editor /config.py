"""
config.py — Configuration for Report Automation System
BRANCH: THANE NEW - Sales Only
"""

import os
import json

# ============================================================
# LOAD SECRETS (Environment Variables / GitHub Secrets)
# ============================================================
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY_THANENEW", "")
SALES_SPREADSHEET_ID = os.environ.get("THANENEW_SALES_SPREADSHEET_ID", "1bAxmZHCByQMPKGZ4Qi2bYzk2NuC3_cLPfgGP5S76VVE")
GOOGLE_CREDENTIALS_DICT = {}

creds_json = os.environ.get("GOOGLE_CREDENTIALS", "")
if creds_json:
    GOOGLE_CREDENTIALS_DICT = json.loads(creds_json)

# ============================================================
# EMPLOYEE LISTS - SALES ONLY
# ============================================================
SALES_EMPLOYEES = [
    "Adit", "Aryan", "Chetan", "Chris",
    "Karan", "Khushi", "Kitiksha", "Mamta", "Rakshan",
    "Sameer", "Tushar", "Yukta", "Vaishnavi", "Zoya", "Vishnu",
]

# ============================================================
# EMAIL TO NAME MAPPING - SALES ONLY
# ============================================================
SALES_EMAIL_MAP = {
    "adit.edujam@gmail.com": "Adit",
    "aryany.edujam@gmail.com": "Aryan",
    "chetang.edujam@gmail.com": "Chetan",
    "chrisa.edujam@gmail.com": "Chris",
    "karanp.edujam@gmail.com": "Karan",
    "khushib.edujam@gmail.com": "Khushi",
    "kitiksha.edujam@gmail.com": "Kitiksha",
    "mamta.edujam@gmail.com": "Mamta",
    "rakshan.edujam@gmail.com": "Rakshan",
    "sameers.edujam@gmail.com": "Sameer",
    "tushark.edujam@gmail.com": "Tushar",
    "yuktam.edujam@gmail.com": "Yukta",
    "vaishnavip.edujam@gmail.com": "Vaishnavi",
    "zoya.edujam@gmail.com": "Zoya",
    "vishnup.edujam@gmail.com": "Vishnu",
}

# ============================================================
# Build Gmail Query with specific senders
# ============================================================
ALL_SALES_EMAILS = list(SALES_EMAIL_MAP.keys())
ALL_ALLOWED_EMAILS = ALL_SALES_EMAILS

FROM_QUERY = " OR ".join([f"from:{email}" for email in ALL_ALLOWED_EMAILS])
GMAIL_QUERY = f"({FROM_QUERY}) is:unread"

# ============================================================
# MAX EMAILS PER RUN
# ============================================================
MAX_EMAILS_PER_RUN = 30

# ============================================================
# SALES DEADLINE RULE - 09:00 PM IST
# ============================================================
SALES_DEADLINE_HOUR = 21
SALES_DEADLINE_MINUTE = 0

# ============================================================
# SCHEDULER ACTIVE WINDOW - 3:00 PM to 09:00 PM IST
# ============================================================
ACTIVE_START_HOUR = 15
ACTIVE_START_MINUTE = 0
ACTIVE_END_HOUR = 21
ACTIVE_END_MINUTE = 0

# ============================================================
# GOOGLE SHEETS CONFIGURATION - SALES ONLY
# ============================================================
DATE_IN_SUBJECT_FORMAT = "%d-%m-%Y"
SHEET_NAME_FORMAT = "%b-%Y"

SALES_COLUMN_MAPPING = {
    "Date": 1,
    "Employee Name": 2,
    "Total Dialed": 3,
    "Total Connected": 4,
    "Duration": 5,
    "Prospect": 6,
    "Ref Added": 7,
    "status Viewed": 8,
    "Document Collected": 9,
    "Report Status": 10,
}

SALES_HEADERS = list(SALES_COLUMN_MAPPING.keys())

# ============================================================
# GMAIL CONFIGURATION
# ============================================================
GMAIL_SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]
GMAIL_USER_ID = "me"

# ============================================================
# GEMINI CONFIGURATION
# ============================================================
GEMINI_MODEL = "gemini-2.5-flash"

# ============================================================
# VALIDATION RULES - SALES ONLY
# ============================================================
VALIDATION_RULES = {
    "Sales": {
        "required_fields": ["Total Dialed", "Total Connected", "Duration"],
        "tolerance_pct": 5,
        "name_fuzzy_threshold": 0.80,
    },
}

DEPARTMENT_KEYWORDS = {
    "Sales": ["sales", "callyzer", "dialer", "prospect", "dialed", "dial", "outgoing", "dails", "prospects"]
}

DATE_PATTERNS = [
    r"(\d{2}-\d{2}-\d{4})",
    r"(\d{2}/\d{2}/\d{4})",
    r"(\d{4}-\d{2}-\d{2})",
]

# ============================================================
# RETRY / RESILIENCE
# ============================================================
MAX_RETRIES = 3
RETRY_MIN_WAIT_SEC = 2
RETRY_MAX_WAIT_SEC = 10

# ============================================================
# LOGGING / TRACKING
# ============================================================
LOG_DIR = "logs"
PROCESSING_LOG_PATH = f"{LOG_DIR}/processing_logs.csv"
ERROR_LOG_PATH = f"{LOG_DIR}/error_logs.jsonl"
DUPLICATE_CACHE_PATH = f"{LOG_DIR}/duplicate_cache.json"
DUPLICATE_WINDOW_HOURS = 24

# ============================================================
# SERVICE ACCOUNT FILE
# ============================================================
SERVICE_ACCOUNT_FILE = "credentials.json"
