#!/usr/bin/env python3
"""
Toggl Track CSV → PDF Time Tracking Report

Usage:
  python generate_report.py [csv_file] [--weekly-target HOURS] [--output FILE]

Defaults:
  csv_file       — auto-detected from csv/ directory (most recent)
  weekly-target  — 42 hours/week  (= 8.4 h/day over 5 days)
  output         — report_YYYYMMDD_HHMMSS.pdf
"""

import argparse
import glob
import os
import sys

import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
import numpy as np
import pandas as pd
from matplotlib.backends.backend_pdf import PdfPages


# ---------------------------------------------------------------------------
# Palette (dark theme)
# ---------------------------------------------------------------------------
BG      = "#1e1e2e"
PANEL   = "#2a2a3e"
LINE    = "#565f89"
GRID    = "#313244"
TEXT    = "#cdd6f4"
SUBTLE  = "#a6adc8"
ACCENT  = "#7aa2f7"
GREEN   = "#9ece6a"
RED     = "#f7768e"
ORANGE  = "#e0af68"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def parse_duration(s: str) -> float:
    """'H:MM:SS' → decimal hours."""
    h, m, sec = (int(x) for x in str(s).strip().split(":"))
    return h + m / 60 + sec / 3600


def fmt_h(hours: float) -> str:
    """Decimal hours → 'Xh MMm' (with sign)."""
    sign = "-" if hours < 0 else ""
    h = abs(hours)
    hh = int(h)
    mm = int(round((h - hh) * 60))
    if mm == 60:
        hh += 1
        mm = 0
    return f"{sign}{hh}h {mm:02d}m"


def setup_rcparams():
    plt.rcParams.update({
        "figure.facecolor":  BG,
        "axes.facecolor":    PANEL,
        "axes.edgecolor":    LINE,
        "axes.labelcolor":   TEXT,
        "xtick.color":       SUBTLE,
        "ytick.color":       SUBTLE,
        "text.color":        TEXT,
        "grid.color":        GRID,
        "grid.linewidth":    0.5,
        "font.family":       "DejaVu Sans",
        "font.size":         9,
    })


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def load_csv(path: str) -> pd.DataFrame:
    df = pd.read_csv(path, skipinitialspace=True)
    df.columns = [c.strip().strip('"') for c in df.columns]

    for col in df.select_dtypes(include="object").columns:
        df[col] = df[col].str.strip().str.strip('"')

    df["hours"]   = df["Duration"].apply(parse_duration)
    df["date"]    = pd.to_datetime(df["Start date"])
    df["weekday"] = df["date"].dt.day_name()
    df["week_key"] = df["date"].dt.strftime("%G-W%V")   # ISO year-week

    if "Start time" in df.columns:
        df["start_hour"] = pd.to_datetime(
            df["Start time"], format="%H:%M:%S", errors="coerce"
        ).dt.hour

    if "Stop time" in df.columns and "Start time" in df.columns:
        df["session_h"] = df["hours"]   # already parsed

    return df


def build_daily(df: pd.DataFrame, daily_target: float) -> pd.DataFrame:
    daily = (
        df.groupby("date")["hours"]
        .sum()
        .reset_index()
        .rename(columns={"hours": "worked"})
    )
    daily["weekday"]    = daily["date"].dt.day_name()
    daily["week_key"]   = daily["date"].dt.strftime("%G-W%V")
    daily["overtime"]   = daily["worked"] - daily_target
    daily["is_weekend"] = daily["date"].dt.weekday >= 5
    return daily.sort_values("date").reset_index(drop=True)


def build_weekly(daily: pd.DataFrame, daily_target: float) -> pd.DataFrame:
    WEEKDAY_ORDER = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

    agg = daily.groupby("week_key").agg(
        worked=("worked", "sum"),
        days=("date", "count"),
    ).reset_index()

    # Target = tracked weekdays × daily_target (holidays excluded, same logic as summary)
    def week_target(row):
        week_days = daily[daily["week_key"] == row["week_key"]]
        weekday_count = (~week_days["is_weekend"]).sum()
        return min(weekday_count, 5) * daily_target

    agg["target"]   = agg.apply(week_target, axis=1)
    agg["overtime"] = agg["worked"] - agg["target"]

    # Per-day hours for the table (Mon–Sun)
    for day in WEEKDAY_ORDER:
        day_data = daily[daily["weekday"] == day].set_index("week_key")["worked"]
        agg[day[:3]] = agg["week_key"].map(day_data)

    # Fill in every week in the date range, including empty ones (holidays / full weeks off)
    date_min = daily["date"].min()
    date_max = daily["date"].max()
    all_weeks = (
        pd.date_range(date_min, date_max, freq="W-MON")  # Monday of each week
        .strftime("%G-W%V")
        .tolist()
    )
    # Also include the week containing date_min if it started before the first Monday
    all_weeks = sorted(set(
        [date_min.strftime("%G-W%V"), date_max.strftime("%G-W%V")] + all_weeks
    ))

    full = pd.DataFrame({"week_key": all_weeks})
    full = full.merge(agg, on="week_key", how="left")
    full["worked"]   = full["worked"].fillna(0.0)
    full["days"]     = full["days"].fillna(0).astype(int)
    full["target"]   = full["target"].fillna(0.0)
    full["overtime"] = full["overtime"].fillna(0.0)

    return full.sort_values("week_key").reset_index(drop=True)


# ---------------------------------------------------------------------------
# Page 1 — Summary + weekly table
# ---------------------------------------------------------------------------

def page_summary(pdf: PdfPages, df: pd.DataFrame, daily: pd.DataFrame,
                 weekly: pd.DataFrame, weekly_target: float, daily_target: float):

    total_worked = daily["worked"].sum()
    date_min, date_max = daily["date"].min(), daily["date"].max()
    tracked_workdays = int((~daily["is_weekend"]).sum())
    expected_total   = tracked_workdays * daily_target
    balance          = total_worked - expected_total
    avg_daily        = total_worked / len(daily)
    weeks_worked     = int((weekly["worked"] > 0).sum())
    avg_weekly       = total_worked / weeks_worked if weeks_worked else 0.0

    member = "Unknown"
    if "Member" in df.columns:
        names = [n for n in df["Member"].dropna().unique() if n and n != "-"]
        if names:
            member = ", ".join(names)

    fig = plt.figure(figsize=(11, 8.5))
    fig.patch.set_facecolor(BG)

    # ── Header ──────────────────────────────────────────────────────────────
    fig.text(0.05, 0.96, "Time Tracking Report",
             fontsize=22, fontweight="bold", color=TEXT, va="top")
    fig.text(0.05, 0.91, member,
             fontsize=13, fontweight="bold", color=ACCENT, va="top")
    fig.text(0.05, 0.875,
             f"{date_min.strftime('%b %d, %Y')}  –  {date_max.strftime('%b %d, %Y')}",
             fontsize=11, color=TEXT, va="top")

    # ── KPI tiles ───────────────────────────────────────────────────────────
    # Each entry: (label, value, expected_or_None, sub_or_None, color)
    half_day        = daily_target / 2
    balance_halfdays = balance / half_day
    balance_sign    = "+" if balance_halfdays >= 0 else ""
    balance_sub     = f"{balance_sign}{balance_halfdays:.1f} half-days"

    kpis = [
        ("Total Worked",    fmt_h(total_worked), fmt_h(expected_total), None,          ACCENT),
        ("Daily Average",   fmt_h(avg_daily),    fmt_h(daily_target),   None,          ACCENT),
        ("Weekly Average",  fmt_h(avg_weekly),   fmt_h(weekly_target),  None,          ACCENT),
        ("Overall Balance", fmt_h(balance),      None,                  balance_sub,   GREEN if balance >= 0 else RED),
        ("Days Tracked",    str(len(daily)),      None,                  None,          ACCENT),
    ]
    tile_w, tile_h = 0.155, 0.10
    gap, x0, y0 = 0.014, 0.05, 0.84

    LABEL_RESERVE = 0.022   # height kept for the label at the bottom
    LINE_H        = {"value": 0.023, "secondary": 0.017}
    LINE_GAP      = 0.004

    for i, (label, value, expected, sub, color) in enumerate(kpis):
        x = x0 + i * (tile_w + gap)
        rect = mpatches.FancyBboxPatch(
            (x, y0 - tile_h), tile_w, tile_h,
            boxstyle="round,pad=0.01",
            facecolor=PANEL, edgecolor=LINE, linewidth=0.8,
            transform=fig.transFigure, figure=fig,
        )
        fig.add_artist(rect)

        # Center the value+secondary block in the space above the label
        content_lines = (
            [("value", value, 12, color)]
            + ([("secondary", f"/ {expected}", 8, SUBTLE)] if expected else [])
            + ([("secondary", sub,             7, SUBTLE)] if sub      else [])
        )
        block_h = sum(
            LINE_H["value" if k == "value" else "secondary"] for k, *_ in content_lines
        ) + LINE_GAP * (len(content_lines) - 1)

        content_area_center = (y0 - tile_h + LABEL_RESERVE + y0 - 0.008) / 2
        y_cur = content_area_center + block_h / 2

        for kind, text, fs, col in content_lines:
            lh = LINE_H[kind if kind == "value" else "secondary"]
            fig.text(x + tile_w / 2, y_cur, text,
                     fontsize=fs, fontweight="bold" if kind == "value" else "normal",
                     color=col, ha="center", va="top")
            y_cur -= lh + LINE_GAP

        fig.text(x + tile_w / 2, y0 - tile_h + 0.008, label,
                 fontsize=9, fontweight="bold", color=TEXT, ha="center", va="bottom")

    # ── Weekly table ────────────────────────────────────────────────────────
    ax = fig.add_axes([0.04, 0.04, 0.92, 0.56])
    ax.set_facecolor(BG)
    ax.axis("off")
    ax.text(0, 1.03, "Weekly Breakdown", fontsize=12, fontweight="bold",
            color=TEXT, transform=ax.transAxes)

    DAY_COLS  = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    META_COLS = ["Week", "Days", "Worked", "Target", "Balance"]
    ALL_COLS  = META_COLS + DAY_COLS
    COL_X     = [0.00, 0.09, 0.17, 0.26, 0.34,
                 0.46, 0.54, 0.62, 0.70, 0.78, 0.86, 0.93]
    ROW_H     = 1.0 / (len(weekly) + 1.5)
    HEADER_Y  = 0.96

    for cx, label in zip(COL_X, ALL_COLS):
        ax.text(cx, HEADER_Y, label, fontsize=8.5, fontweight="bold",
                color=SUBTLE, transform=ax.transAxes)

    for i, row in weekly.iterrows():
        y = HEADER_Y - (i + 1) * ROW_H
        if i % 2 == 0:
            ax.add_patch(mpatches.FancyBboxPatch(
                (-0.01, y - ROW_H * 0.15), 1.02, ROW_H * 0.9,
                boxstyle="square,pad=0",
                facecolor=PANEL, edgecolor="none",
                transform=ax.transAxes,
            ))

        ot_str   = ("+" if row["overtime"] >= 0 else "") + fmt_h(row["overtime"])
        ot_color = GREEN if row["overtime"] >= 0 else RED

        meta_vals = [
            (row["week_key"],        TEXT),
            (str(int(row["days"])),  TEXT),
            (fmt_h(row["worked"]),   ACCENT),
            (fmt_h(row["target"]),   SUBTLE),
            (ot_str,                 ot_color),
        ]
        for cx, (val, col) in zip(COL_X[:5], meta_vals):
            ax.text(cx, y + ROW_H * 0.25, val, fontsize=8.5, color=col,
                    transform=ax.transAxes)

        for cx, day in zip(COL_X[5:], DAY_COLS):
            h = row.get(day)
            if pd.notna(h):
                diff = h - daily_target
                col = LINE if day in ("Sat", "Sun") else (
                    GREEN if diff >= 0 else RED if diff < -1 else ORANGE
                )
                ax.text(cx, y + ROW_H * 0.25, fmt_h(h), fontsize=7.5,
                        color=col, transform=ax.transAxes)
            else:
                ax.text(cx, y + ROW_H * 0.25, "—", fontsize=7.5,
                        color=LINE, transform=ax.transAxes)

    pdf.savefig(fig, bbox_inches="tight")
    plt.close(fig)


# ---------------------------------------------------------------------------
# Page 2 — Daily histogram
# ---------------------------------------------------------------------------

def page_daily_charts(pdf: PdfPages, daily: pd.DataFrame, daily_target: float):
    fig, ax_bar = plt.subplots(1, 1, figsize=(11, 8.5))
    fig.patch.set_facecolor(BG)
    fig.subplots_adjust(left=0.07, right=0.97, top=0.94, bottom=0.10)

    x          = np.arange(len(daily))
    hours_arr  = daily["worked"].values
    ot_arr     = daily["overtime"].values
    weekend    = daily["is_weekend"].values

    bar_colors = [
        LINE   if wk else
        GREEN  if ot >= 0 else
        RED    if ot < -1 else
        ORANGE
        for ot, wk in zip(ot_arr, weekend)
    ]

    # ── Bar chart ───────────────────────────────────────────────────────────
    ax_bar.bar(x, hours_arr, color=bar_colors, width=0.7, zorder=2)
    ax_bar.axhline(daily_target, color=ACCENT, linestyle="--", linewidth=1.3, zorder=3)

    for xi, (h, ot) in enumerate(zip(hours_arr, ot_arr)):
        if abs(ot) > 0.33:
            sign = "+" if ot > 0 else ""
            ax_bar.text(xi, h + 0.12, f"{sign}{fmt_h(ot)}",
                        ha="center", va="bottom", fontsize=6,
                        color=GREEN if ot > 0 else RED)

    ax_bar.set_title("Daily Hours Worked", fontsize=12, fontweight="bold", color=TEXT, pad=8)
    ax_bar.set_ylabel("Hours Worked", color=TEXT)
    ax_bar.set_xticks(x)
    ax_bar.set_xticklabels(
        [d.strftime("%b %d\n%a") for d in daily["date"]], fontsize=7
    )
    ax_bar.yaxis.set_major_formatter(ticker.FuncFormatter(lambda v, _: fmt_h(v)))
    ax_bar.grid(axis="y", zorder=0)

    legend_handles = [
        mpatches.Patch(color=GREEN,  label="Over target"),
        mpatches.Patch(color=ORANGE, label="Slightly under (<1 h)"),
        mpatches.Patch(color=RED,    label="Under target (>1 h)"),
        mpatches.Patch(color=LINE,   label="Weekend"),
        plt.Line2D([0], [0], color=ACCENT, linestyle="--",
                   label=f"Daily target ({fmt_h(daily_target)})"),
    ]
    ax_bar.legend(handles=legend_handles, fontsize=8,
                  facecolor=PANEL, edgecolor=LINE, labelcolor=TEXT, loc="upper right")

    pdf.savefig(fig, bbox_inches="tight")
    plt.close(fig)


# ---------------------------------------------------------------------------
# Page 3 — Detailed session log
# ---------------------------------------------------------------------------

def page_detail(pdf: PdfPages, df: pd.DataFrame, daily: pd.DataFrame, daily_target: float):
    ROWS_PER_PAGE = 35

    # Build one row per session, sorted by date then start time
    sessions = df.copy()
    sessions = sessions.sort_values(["Start date", "Start time"]).reset_index(drop=True)

    # Assemble display rows: day header + session rows + break rows between sessions
    rows = []  # ("header", date) | ("session", ...) | ("break", gap_h)
    for date, grp in sessions.groupby("date"):
        rows.append(("header", date))
        grp_sorted = grp.sort_values("Start time").reset_index(drop=True)
        for i, s in grp_sorted.iterrows():
            rows.append(("session", date, s["Start time"][:5], s["Stop time"][:5], s["hours"]))
            if i < len(grp_sorted) - 1:
                next_start = pd.to_datetime(grp_sorted.loc[i + 1, "Start time"], format="%H:%M:%S")
                cur_stop   = pd.to_datetime(s["Stop time"], format="%H:%M:%S")
                gap_h      = (next_start - cur_stop).total_seconds() / 3600
                if gap_h > 1/12:  # only show breaks > 5 min
                    rows.append(("break", gap_h))

    # Paginate
    for page_start in range(0, len(rows), ROWS_PER_PAGE):
        chunk = rows[page_start:page_start + ROWS_PER_PAGE]

        fig = plt.figure(figsize=(11, 8.5))
        fig.patch.set_facecolor(BG)
        fig.text(0.05, 0.96, "Detailed Session Log",
                 fontsize=14, fontweight="bold", color=TEXT, va="top")

        ax = fig.add_axes([0.04, 0.04, 0.92, 0.88])
        ax.set_facecolor(BG)
        ax.axis("off")

        # Column positions and headers
        COL_X     = [0.00, 0.28, 0.46, 0.60, 0.75]
        COL_HEADS = ["Date", "Start", "Stop", "Duration", "Daily Total"]
        HEADER_Y  = 0.97

        for cx, head in zip(COL_X, COL_HEADS):
            ax.text(cx, HEADER_Y, head, fontsize=9, fontweight="bold",
                    color=SUBTLE, transform=ax.transAxes)

        ax.plot([0, 1], [HEADER_Y - 0.012, HEADER_Y - 0.012], color=LINE,
                linewidth=0.6, transform=ax.transAxes)

        row_h  = (HEADER_Y - 0.012) / (ROWS_PER_PAGE + 1)
        y      = HEADER_Y - 0.012 - row_h * 0.5
        daily_hours = dict(zip(daily["date"], daily["worked"]))
        SESSION_INDENT = 0.03

        for i, entry in enumerate(chunk):
            y -= row_h
            if entry[0] == "header":
                date    = entry[1]
                worked  = daily_hours.get(date, 0)
                ot      = worked - daily_target
                is_wknd = date.weekday() >= 5

                # Separator line above every day block except the very first
                if i > 0:
                    ax.plot([0, 1], [y + row_h * 0.72, y + row_h * 0.72],
                            color=LINE, linewidth=0.8, transform=ax.transAxes)

                # Background band for the day header
                ax.add_patch(mpatches.Rectangle(
                    (0, y - row_h * 0.32), 1, row_h * 1.1,
                    facecolor=PANEL, edgecolor="none",
                    transform=ax.transAxes, clip_on=False,
                ))

                ax.text(COL_X[0], y, date.strftime("%A, %b %-d %Y"),
                        fontsize=9, fontweight="bold",
                        color=SUBTLE if is_wknd else TEXT, transform=ax.transAxes)

                if not is_wknd:
                    ot_str   = ("+" if ot >= 0 else "") + fmt_h(ot)
                    ot_color = GREEN if ot >= 0 else RED if ot < -1 else ORANGE
                    ax.text(COL_X[3], y, fmt_h(worked), fontsize=9, fontweight="bold",
                            color=ACCENT, transform=ax.transAxes)
                    ax.text(COL_X[4], y, ot_str, fontsize=9, fontweight="bold",
                            color=ot_color, transform=ax.transAxes)

            elif entry[0] == "session":
                _, date, start, stop, duration = entry
                ax.text(COL_X[1] + SESSION_INDENT, y, start,
                        fontsize=8.5, color=TEXT,   transform=ax.transAxes)
                ax.text(COL_X[2] + SESSION_INDENT, y, stop,
                        fontsize=8.5, color=TEXT,   transform=ax.transAxes)
                ax.text(COL_X[3] + SESSION_INDENT, y, fmt_h(duration),
                        fontsize=8.5, color=SUBTLE, transform=ax.transAxes)

            else:  # break
                gap_h = entry[1]
                ax.text(COL_X[1] + SESSION_INDENT, y, f"break  {fmt_h(gap_h)}",
                        fontsize=7.5, color=LINE, style="italic", transform=ax.transAxes)

        pdf.savefig(fig, bbox_inches="tight")
        plt.close(fig)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Generate PDF time tracking report from Toggl CSV"
    )
    parser.add_argument("csv", nargs="?",
                        help="Path to CSV (auto-detected from csv/ if omitted)")
    parser.add_argument("--weekly-target", type=float, default=42.0,
                        metavar="HOURS",
                        help="Target hours per week (default: 42)")
    parser.add_argument("--output", "-o", default=None,
                        help="Output PDF path")
    args = parser.parse_args()

    # Locate CSV
    if args.csv:
        csv_path = args.csv
    else:
        pattern = os.path.join(os.path.dirname(os.path.abspath(__file__)), "csv", "*.csv")
        files = sorted(glob.glob(pattern))
        if not files:
            sys.exit("No CSV files found in csv/ directory.")
        csv_path = files[-1]
        print(f"Using: {csv_path}")

    weekly_target = args.weekly_target
    daily_target  = weekly_target / 5

    setup_rcparams()

    df     = load_csv(csv_path)
    daily  = build_daily(df, daily_target)

    if args.output:
        output_path = args.output
    else:
        reports_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "reports")
        os.makedirs(reports_dir, exist_ok=True)
        d_min = daily["date"].min().strftime("%Y%m%d")
        d_max = daily["date"].max().strftime("%Y%m%d")
        output_path = os.path.join(reports_dir, f"report_{d_min}_{d_max}.pdf")
    weekly = build_weekly(daily, daily_target)

    with PdfPages(output_path) as pdf:
        page_summary(pdf, df, daily, weekly, weekly_target, daily_target)
        page_daily_charts(pdf, daily, daily_target)
        page_detail(pdf, df, daily, daily_target)

    print(f"Report saved → {output_path}")


if __name__ == "__main__":
    main()
