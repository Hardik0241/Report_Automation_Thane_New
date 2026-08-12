"""
config.py — Complete configuration for Report Automation System
BRANCH REPO VERSION - Sales Only
"""

import os
import json

# ============================================================
# LOAD SECRETS (Environment Variables / GitHub Secrets)
# ============================================================
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
SALES_SPREADSHEET_ID = os.environ.get("SALES_SPREADSHEET_ID", "")
# HR_SPREADSHEET_ID not needed for branch repos
GOOGLE_CREDENTIALS_DICT = {}

creds_json = os.environ.get("GOOGLE_CREDENTIALS", "")
if creds_json:
    GOOGLE_CREDENTIALS_DICT = json.loads(creds_json)

# ============================================================
# EMPLOYEE LISTS - SALES ONLY
# ============================================================
# ⚠️ UPDATE THIS LIST WITH BRANCH-SPECIFIC EMPLOYEES
SALES_EMPLOYEES = [
    # Add branch employees here
    # Example: "Employee1", "Employee2", "Employee3",
]

HR_EMPLOYEES = []  # No HR for branch repos

# ============================================================
# EMAIL TO NAME MAPPING - SALES ONLY
# ============================================================
# ⚠️ UPDATE THIS MAP WITH BRANCH-SPECIFIC EMAILS
SALES_EMAIL_MAP = {
    # Add branch emails here
    # Example: "employee1.branch@gmail.com": "Employee1",
}

HR_EMAIL_MAP = {}  # No HR for branch repos

# ============================================================
# Build Gmail Query with specific senders
# ============================================================
ALL_SALES_EMAILS = list(SALES_EMAIL_MAP.keys())
ALL_HR_EMAILS = []  # No HR
ALL_ALLOWED_EMAILS = ALL_SALES_EMAILS + ALL_HR_EMAILS

FROM_QUERY = " OR ".join([f"from:{email}" for email in ALL_ALLOWED_EMAILS])
GMAIL_QUERY = f"({FROM_QUERY}) is:unread"

# ============================================================
# MAX EMAILS PER RUN - Process ALL emails
# ============================================================
MAX_EMAILS_PER_RUN = 30

# ============================================================
# SALES DEADLINE RULE - 09:00 PM IST
# ============================================================
SALES_DEADLINE_HOUR = 21    # 09:00 PM
SALES_DEADLINE_MINUTE = 0

# ============================================================
# SCHEDULER ACTIVE WINDOW - 3:00 PM to 09:00 PM IST
# ============================================================
ACTIVE_START_HOUR = 15      # 3:00 PM
ACTIVE_START_MINUTE = 0
ACTIVE_END_HOUR = 21        # 09:00 PM
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

# No HR column mapping for branch repos
HR_COLUMN_MAPPING = {}

SALES_HEADERS = list(SALES_COLUMN_MAPPING.keys())
HR_HEADERS = []  # No HR headers

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
    # No HR validation rules
}

DEPARTMENT_KEYWORDS = {
    "Sales": ["sales", "callyzer", "dialer", "prospect", "dialed", "dial", "outgoing"],
    "HR": [],  # No HR keywords
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

