# Time Tracking Report Generator

Generates a PDF report from a [Toggl Track](https://toggl.com/track/) detailed CSV export.

## Requirements

```bash
pip install pandas matplotlib numpy
```

## Usage

```bash
python generate_report.py [csv_file] [--weekly-target HOURS] [--output FILE]
```

- `csv_file` — path to the CSV (auto-detected from `csv/` if omitted)
- `--weekly-target` — target hours per week (default: `42`)
- `--output` / `-o` — output PDF path (default: `report_YYYYMMDD_YYYYMMDD.pdf`)

## Getting the CSV

### Option A — API (recommended)

1. Copy `.toggl_api_key.example` to `.toggl_api_key` and paste your Toggl API token (find it at **toggl.com/profile** → *API Token*).
2. Run:

```bash
python fetch_report.py --start-date 2026-06-01 --end-date 2026-06-17
```

This saves `csv/toggl_2026-06-01_2026-06-17.csv`, ready to pass straight to `generate_report.py`.

```
python fetch_report.py --start-date YYYY-MM-DD [--end-date YYYY-MM-DD] [--output FILE]
```

- `--end-date` defaults to today
- `--output` defaults to `csv/toggl_<start>_<end>.csv`

### Option B — Manual export

In Toggl Track → **Reports** → **Detailed** → select date range → **Export CSV**.

## Report contents

| Page | Content |
|------|---------|
| 1 | KPI summary + weekly breakdown table |
| 2 | Daily hours histogram |
| 3 | Detailed session log with breaks |

**Notes on targets:** weekends and days with no logged hours (holidays, days off) are excluded from the expected total — only days you actually worked count toward the target.
