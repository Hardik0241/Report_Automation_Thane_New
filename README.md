# 📊 Thane New - Report Automation System

## 📋 Overview
This repository automates the collection and processing of daily sales reports for the **Thane New Branch**. It reads unread emails from a dedicated Gmail account, extracts data using Gemini AI, validates against screenshots (if available), and writes structured data to a Google Sheet.

---

## 🚀 Features

- ✅ **Automated Email Fetching** - Reads unread emails from Thane New branch employees
- ✅ **AI-Powered Data Extraction** - Uses Gemini AI to parse email body and screenshots
- ✅ **Duplicate Prevention** - Prevents processing the same email twice (24-hour cache)
- ✅ **Late Submission Tracking** - Marks employees as "Not Sent" if submitted after 9:00 PM IST
- ✅ **Google Sheets Integration** - Writes data to Thane New's dedicated Google Sheet
- ✅ **Retry Logic** - Handles API failures (503 errors, quota limits) with automatic retries
- ✅ **Read-Only Gmail Access** - Emails remain unread after processing

---

## 🛠️ Tech Stack

| Component | Technology |
|-----------|------------|
| **Email Reading** | Gmail API (OAuth 2.0) |
| **AI Parsing** | Gemini API (Text + Vision) |
| **Screenshot Parsing** | Gemini Vision + Tesseract OCR (Fallback) |
| **Data Storage** | Google Sheets API (Service Account) |
| **Scheduling** | GitHub Actions (3:00 PM - 9:00 PM IST) |
| **Language** | Python 3.11 |

---

## 📁 Repository Structure


Report_Automation_ThaneNew/
├── .github/
│ └── workflows/
│ └── scheduler.yml ← GitHub Actions schedule
├── Working_Report_Editor/
│ ├── config.py ← Branch configuration
│ ├── config.yaml ← Model configuration
│ ├── error_handler.py ← Error handling & retry logic
│ ├── gemini_parser.py ← Email body parser
│ ├── gmail_reader.py ← Gmail email fetcher
│ ├── main.py ← Main orchestrator
│ ├── requirements.txt ← Python dependencies
│ ├── runtime.txt ← Python version
│ ├── sheets_service.py ← Google Sheets writer
│ ├── tracker.py ← Duplicate detection & logging
│ ├── utils.py ← Helper functions
│ ├── validator.py ← Data validation
│ └── vision_parser.py ← Screenshot parser
├── .gitignore ← Git ignore rules
├── .python-version ← Python version
└── README.md ← This file


---

## 🔑 Configuration

### Google Sheets Structure (Sales Only)

| Column | Header |
|--------|--------|
| A | Date |
| B | Employee Name |
| C | Total Dialed |
| D | Total Connected |
| E | Duration |
| F | Prospect |
| G | Ref Added |
| H | status Viewed |
| I | Document Collected |
| J | Report Status |

### Report Status Values

| Status | Meaning |
|--------|---------|
| **(blank)** | ✅ Data written successfully |
| `Not Sent` | ⚠️ Employee didn't submit OR submitted after 9:00 PM |

---

## 🔐 GitHub Secrets Required

| Secret Name | Purpose |
|-------------|---------|
| `THANENEW_CLIENT_ID` | Gmail OAuth Client ID |
| `THANENEW_CLIENT_SECRET` | Gmail OAuth Client Secret |
| `THANENEW_REFRESH_TOKEN` | Gmail OAuth Refresh Token |
| `GEMINI_API_KEY_THANENEW` | Gemini API Key |
| `THANENEW_SALES_SPREADSHEET_ID` | Google Sheet ID |
| `GOOGLE_CREDENTIALS` | Service Account JSON |

---

## ⏰ Schedule

The system runs automatically via GitHub Actions:

| Time (IST) | Action |
|------------|--------|
| 3:00 PM - 8:30 PM | Runs every 30 minutes |
| 9:00 PM | Final run (deadline) |

**Sales employees submitting after 9:00 PM are marked as "Not Sent"**

---

## 📧 Supported Email Formats

### Duration Formats

| Format | Example | Output |
|--------|---------|--------|
| Standard | `01:28:52` | 01:28:52 |
| Dots (2-digit hour) | `02.07.36` | 02:07:36 |
| Dots (1-digit hour) | `2.08.32` | 02:08:32 |
| Single digit seconds | `01:28:0` | 01:28:00 |
| Text (h/m/s) | `1h 42m 8s` | 01:42:08 |
| `sec` as seconds | `1h 42m 8sec` | 01:42:08 |
| `min` as minutes | `1hr 25min 46s` | 01:25:46 |
| `MINS SEC` (uppercase) | `49 MINS 9 SEC` | 00:49:09 |
| Addition patterns | `1h 15m + 10 min` | 01:25:00 |

### Department Detection
- **Sales:** Keywords like "dialed", "connected", "prospect"

---

## 🚀 Local Development

Clone the repository:
  
  git clone https://github.com/your-org/Report_Automation_ThaneNew.git
  cd Report_Automation_ThaneNew/Working_Report_Editor
  pip install -r requirements.txt
  export CLIENT_ID=your_client_id
  export CLIENT_SECRET=your_client_secret
  export REFRESH_TOKEN=your_refresh_token
  export GEMINI_API_KEY=your_gemini_api_key
  export SALES_SPREADSHEET_ID=your_sheet_id
  export GOOGLE_CREDENTIALS='{"your":"json"}'
  python main.py

📊 Flow Diagram

┌─────────────────────────────────────────────────────────────────┐
│                    GITHUB ACTIONS (Scheduler)                   │
│  Runs every 30 min from 3:00 PM - 9:00 PM IST                  │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                    GMAIL API (Read Only)                        │
│  Fetches unread emails from Thane New branch employees         │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                    GEMINI AI (Text + Vision)                    │
│  Extracts: Calls, Connected, Duration, Prospect                │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                    GOOGLE SHEETS API                            │
│  Writes data to Thane New Sales Sheet                          │
└─────────────────────────────────────────────────────────────────┘


---

## 📋 What's Included

| Section | Purpose |
|---------|---------|
| **Overview** | Brief description of the system |
| **Features** | Key capabilities |
| **Tech Stack** | Technologies used |
| **Repository Structure** | File/folder layout |
| **Configuration** | Sheet structure and status values |
| **GitHub Secrets** | Required secrets for the branch |
| **Schedule** | When the system runs |
| **Supported Formats** | Duration and department detection |
| **Local Development** | How to run locally |
| **Flow Diagram** | Visual representation of the pipeline |
| **Error Handling** | How errors are managed |
| **Notes** | Important branch-specific details |

---

**Copy this `README.md` to your Thane New Branch Repo.**
