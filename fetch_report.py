#!/usr/bin/env python3
"""
Fetch a Toggl Track detailed CSV report via the API and save it to csv/.

Usage:
    python fetch_report.py --start-date 2026-06-01 --end-date 2026-06-17
    python fetch_report.py --start-date 2026-06-01          # end-date defaults to today
    python fetch_report.py --start-date 2026-06-01 --output csv/custom_name.csv
"""

import argparse
import os
import sys
from datetime import date, datetime
from pathlib import Path

import requests

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

API_KEY_FILE = Path(__file__).parent / ".toggl_api_key"
WORKSPACES_URL = "https://api.track.toggl.com/api/v9/me/workspaces"
REPORT_URL_TEMPLATE = (
    "https://api.track.toggl.com/reports/api/v3/workspace/{workspace_id}"
    "/search/time_entries.csv"
)

# Column names returned by the API → names expected by generate_report.py
COLUMN_RENAMES = {
    "User": "Member",
    "End date": "Stop date",
    "End time": "Stop time",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def load_api_key() -> str:
    if not API_KEY_FILE.exists():
        sys.exit(
            f"Error: API key file not found at {API_KEY_FILE}\n"
            "Copy .toggl_api_key.example to .toggl_api_key and paste your API token."
        )
    key = API_KEY_FILE.read_text().strip()
    if not key or key == "YOUR_API_KEY_HERE":
        sys.exit(
            f"Error: {API_KEY_FILE} still contains the placeholder value.\n"
            "Open the file and replace YOUR_API_KEY_HERE with your Toggl API token.\n"
            "Find it at: https://track.toggl.com/profile → 'API Token'."
        )
    return key


def get_workspace_id(api_key: str) -> int:
    response = requests.get(
        WORKSPACES_URL,
        auth=(api_key, "api_token"),
        timeout=30,
    )
    if response.status_code == 403:
        sys.exit("Error: Invalid API key (HTTP 403). Check the token in .toggl_api_key.")
    response.raise_for_status()
    workspaces = response.json()
    if not workspaces:
        sys.exit("Error: No workspaces found for this API key.")
    return workspaces[0]["id"]


def fetch_csv_bytes(api_key: str, workspace_id: int, start_date: str, end_date: str) -> bytes:
    response = requests.post(
        REPORT_URL_TEMPLATE.format(workspace_id=workspace_id),
        auth=(api_key, "api_token"),
        json={"start_date": start_date, "end_date": end_date},
        timeout=60,
    )
    response.raise_for_status()
    return response.content


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fetch a Toggl Track detailed CSV report via the API."
    )
    parser.add_argument(
        "--start-date",
        required=True,
        metavar="YYYY-MM-DD",
        help="Start of the report period (inclusive).",
    )
    parser.add_argument(
        "--end-date",
        default=date.today().isoformat(),
        metavar="YYYY-MM-DD",
        help="End of the report period (inclusive). Defaults to today.",
    )
    parser.add_argument(
        "--output",
        "-o",
        default=None,
        metavar="FILE",
        help=(
            "Output CSV path. Defaults to "
            "csv/toggl_<start-date>_<end-date>.csv"
        ),
    )
    return parser.parse_args()


def validate_date(value: str, name: str) -> None:
    try:
        datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        sys.exit(f"Error: {name} '{value}' is not a valid YYYY-MM-DD date.")


def main() -> None:
    args = parse_args()

    validate_date(args.start_date, "--start-date")
    validate_date(args.end_date, "--end-date")

    if args.output is None:
        output_path = Path("csv") / f"toggl_{args.start_date}_{args.end_date}.csv"
    else:
        output_path = Path(args.output)

    output_path.parent.mkdir(parents=True, exist_ok=True)

    print("Reading API key...")
    api_key = load_api_key()

    print("Fetching workspace ID...")
    workspace_id = get_workspace_id(api_key)
    print(f"  → workspace {workspace_id}")

    print(f"Downloading report ({args.start_date} → {args.end_date})...")
    csv_bytes = fetch_csv_bytes(api_key, workspace_id, args.start_date, args.end_date)

    # Parse, rename columns to match generate_report.py, and re-save.
    import io
    import pandas as pd

    df = pd.read_csv(io.BytesIO(csv_bytes), skipinitialspace=True)
    df.columns = [c.strip().strip('"') for c in df.columns]
    df.rename(columns=COLUMN_RENAMES, inplace=True)
    df.to_csv(output_path, index=False)

    print(f"Saved {len(df)} rows → {output_path}")


if __name__ == "__main__":
    main()
