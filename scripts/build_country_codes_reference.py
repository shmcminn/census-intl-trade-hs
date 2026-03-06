#!/usr/bin/env python3
"""
Build a local CTY_CODE reference table for this skill.

This pulls annual total rows from both imports/hs and exports/hs,
then keeps 4-digit numeric country codes only.
"""

from __future__ import annotations

import json
import urllib.parse
import urllib.request
from pathlib import Path

import pandas as pd


BASE = "https://api.census.gov/data/timeseries/intltrade"
OUTPUT = Path(__file__).resolve().parent.parent / "references" / "country_codes.csv"


def fetch_flow(flow: str, commodity_param: str) -> pd.DataFrame:
    params = {
        "get": "YEAR,CTY_CODE,CTY_NAME",
        "YEAR": "*",
        "MONTH": "12",
        commodity_param: "-",
        "CTY_CODE": "*",
    }
    url = f"{BASE}/{flow}?{urllib.parse.urlencode(params)}"
    with urllib.request.urlopen(url, timeout=120) as response:
        raw = json.loads(response.read().decode("utf-8"))

    if not raw or len(raw) <= 1:
        return pd.DataFrame(columns=["YEAR", "CTY_CODE", "CTY_NAME", "flow"])

    headers = raw[0]
    keep_idx = []
    seen = set()
    for i, name in enumerate(headers):
        if name in seen:
            continue
        seen.add(name)
        keep_idx.append(i)

    rows = [[r[i] if i < len(r) else "" for i in keep_idx] for r in raw[1:]]
    clean_headers = [headers[i] for i in keep_idx]
    frame = pd.DataFrame(rows, columns=clean_headers)
    if {"YEAR", "CTY_CODE", "CTY_NAME"} - set(frame.columns):
        return pd.DataFrame(columns=["YEAR", "CTY_CODE", "CTY_NAME", "flow"])

    frame = frame[["YEAR", "CTY_CODE", "CTY_NAME"]].copy()
    frame["flow"] = flow
    return frame


def main() -> None:
    imports = fetch_flow("imports/hs", "I_COMMODITY")
    exports = fetch_flow("exports/hs", "E_COMMODITY")
    all_rows = pd.concat([imports, exports], ignore_index=True)
    if all_rows.empty:
        raise SystemExit("No country rows returned from Census API.")

    all_rows["YEAR"] = pd.to_numeric(all_rows["YEAR"], errors="coerce")
    all_rows["CTY_CODE"] = all_rows["CTY_CODE"].astype(str).str.strip()
    all_rows["CTY_NAME"] = all_rows["CTY_NAME"].astype(str).str.strip()

    # Keep country rows only and drop regional/treaty aggregates.
    all_rows = all_rows[all_rows["CTY_CODE"].str.fullmatch(r"\d{4}")].copy()
    all_rows = all_rows[all_rows["CTY_CODE"].astype(int) >= 1000].copy()

    grouped = (
        all_rows.sort_values(["CTY_CODE", "YEAR"])
        .groupby("CTY_CODE", as_index=False)
        .agg(
            first_year_seen=("YEAR", "min"),
            latest_year_seen=("YEAR", "max"),
            source_flows=("flow", lambda s: ",".join(sorted(set(s)))),
        )
    )
    latest_name = (
        all_rows.sort_values(["CTY_CODE", "YEAR"])
        .dropna(subset=["YEAR"])
        .groupby("CTY_CODE", as_index=False)
        .tail(1)[["CTY_CODE", "CTY_NAME"]]
    )

    out = grouped.merge(latest_name, on="CTY_CODE", how="left")
    out = out[["CTY_CODE", "CTY_NAME", "first_year_seen", "latest_year_seen", "source_flows"]]
    out["CTY_NAME_NORM"] = (
        out["CTY_NAME"]
        .str.upper()
        .str.replace(r"[^A-Z0-9 ]+", " ", regex=True)
        .str.replace(r"\s+", " ", regex=True)
        .str.strip()
    )
    out = out.sort_values("CTY_CODE").reset_index(drop=True)

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(OUTPUT, index=False)

    print(f"Wrote {len(out)} rows to {OUTPUT}")
    print(out.head(10).to_csv(index=False))


if __name__ == "__main__":
    main()
