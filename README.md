# Time Tracking Report Generator

Generates a PDF report from a [Toggl Track](https://toggl.com/track/) detailed CSV export.

## Usage

```bash
python generate_report.py [csv_file] [--weekly-target HOURS] [--output FILE]
```

- `csv_file` — path to the CSV (auto-detected from `csv/` if omitted)
- `--weekly-target` — target hours per week (default: `42`)
- `--output` / `-o` — output PDF path (default: `report_YYYYMMDD_YYYYMMDD.pdf`)

## Getting the CSV

In Toggl Track → **Reports** → **Detailed** → select date range → **Export CSV**.

## Report contents

| Page | Content |
|------|---------|
| 1 | KPI summary + weekly breakdown table |
| 2 | Daily hours histogram |
| 3 | Detailed session log with breaks |

**Notes on targets:** weekends and days with no logged hours (holidays, days off) are excluded from the expected total — only days you actually worked count toward the target.

## Requirements

```bash
pip install pandas matplotlib numpy
```
