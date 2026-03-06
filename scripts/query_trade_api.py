#!/usr/bin/env python3
"""
Query Census International Trade API with HS scope safeguards.

This script is intentionally strict: if HS codes are provided, it requires
an explicit --confirm-scope flag before running the API request.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
from pathlib import Path
import re
import sys
import urllib.parse
import urllib.request
from typing import Dict, List, Tuple, Union


BASE_URL = "https://api.census.gov/data/timeseries/intltrade"
VALID_HS_LENGTHS = {2, 4, 6, 8}
COUNTRY_NAME_ALIASES = {
    "SOUTH KOREA": "KOREA, SOUTH",
    "KOREA SOUTH": "KOREA, SOUTH",
    "NORTH KOREA": "KOREA, NORTH",
    "RUSSIA": "RUSSIAN FEDERATION",
    "VIET NAM": "VIETNAM",
}
DEFAULT_COUNTRY_CODES_PATH = (
    Path(__file__).resolve().parent.parent / "references" / "country_codes.csv"
)


def load_api_key_from_codex_env(path: str = "~/.codex/census.env") -> str:
    """Load CENSUS_API_KEY from a simple KEY=VALUE file if present."""
    expanded = os.path.expanduser(path)
    if not os.path.exists(expanded):
        return ""
    try:
        with open(expanded, "r", encoding="utf-8") as f:
            for line in f:
                raw = line.strip()
                if not raw or raw.startswith("#"):
                    continue
                if raw.startswith("export "):
                    raw = raw[len("export ") :].strip()
                if "=" not in raw:
                    continue
                key, value = raw.split("=", 1)
                if key.strip() != "CENSUS_API_KEY":
                    continue
                value = value.strip().strip("'").strip('"')
                return value
    except OSError:
        return ""
    return ""


def parse_key_value(items: List[str]) -> Dict[str, Union[str, List[str]]]:
    parsed: Dict[str, Union[str, List[str]]] = {}
    for item in items:
        if "=" not in item:
            raise ValueError(f"Invalid --param value '{item}'. Expected KEY=VALUE.")
        key, value = item.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key:
            raise ValueError(f"Invalid --param value '{item}'. Key is empty.")
        parsed[key] = value
    return parsed


def parse_year_values(raw_year: str) -> List[str]:
    """Parse YEAR input such as '2024,2025'."""
    raw = raw_year.strip()
    if not raw:
        return []
    if raw == "*" or raw.isdigit():
        return [raw]
    if "," in raw:
        vals = [x.strip() for x in raw.split(",") if x.strip()]
        return vals
    return [raw]


def parse_year_range(raw_year: str) -> Tuple[int, int] | None:
    """Parse YEAR range syntax like '2016-2025'."""
    match = re.fullmatch(r"\s*(\d{4})\s*-\s*(\d{4})\s*", raw_year)
    if not match:
        return None
    start = int(match.group(1))
    end = int(match.group(2))
    if start > end:
        return None
    return (start, end)


def month_bounds_for_time(month_value: Union[str, List[str], None]) -> Tuple[str, str] | None:
    """
    Return YYYY-MM bounds to pair with YEAR ranges for `time=from ... to ...`.

    If MONTH is a single numeric value, keep that month at both ends.
    If MONTH is '*' or missing, span full years (Jan to Dec).
    """
    if month_value is None:
        return ("01", "12")
    if isinstance(month_value, list):
        return None

    month_raw = month_value.strip()
    if not month_raw or month_raw == "*":
        return ("01", "12")
    if month_raw.isdigit():
        month_int = int(month_raw)
        if 1 <= month_int <= 12:
            month = f"{month_int:02d}"
            return (month, month)
    return None


def parse_hs_codes(raw_codes: str) -> List[str]:
    if not raw_codes:
        return []
    tokens = re.split(r"[\s,;]+", raw_codes.strip())
    normalized: List[str] = []
    for token in tokens:
        if not token:
            continue
        digits = re.sub(r"\D", "", token)
        if len(digits) not in VALID_HS_LENGTHS:
            raise ValueError(
                f"HS code '{token}' normalized to '{digits}' has invalid length. "
                "Allowed lengths: 2, 4, 6, 8."
            )
        normalized.append(digits)
    if not normalized:
        raise ValueError("No valid HS codes were parsed from --hs-codes input.")
    return sorted(set(normalized))


def redact_key(url: str) -> str:
    return re.sub(r"(key=)[^&]+", r"\1REDACTED", url)


def build_url(
    path: str, params: Dict[str, Union[str, List[str]]], api_key: str | None
) -> str:
    clean_path = path.strip().lstrip("/")
    if not clean_path:
        raise ValueError("--path is required.")

    merged: Dict[str, Union[str, List[str]]] = dict(params)
    if api_key:
        merged["key"] = api_key

    query = urllib.parse.urlencode(merged, doseq=True)
    return f"{BASE_URL}/{clean_path}?{query}" if query else f"{BASE_URL}/{clean_path}"


def normalize_country_name(raw_name: str) -> str:
    """Normalize country text for matching in alias rules."""
    name = re.sub(r"[^A-Z0-9 ]+", " ", raw_name.upper())
    name = re.sub(r"\s+", " ", name).strip()
    return name


def country_retry_candidates(raw_name: str) -> List[str]:
    """Build candidate CTY_NAME retries using aliases and simple transforms."""
    candidates: List[str] = []
    normalized = normalize_country_name(raw_name)
    alias = COUNTRY_NAME_ALIASES.get(normalized)
    if alias and alias.upper() != raw_name.upper():
        candidates.append(alias)
    # Also try normalized words with comma swap pattern for likely 'KOREA SOUTH' style.
    if normalized.endswith(" SOUTH"):
        base = normalized.replace(" SOUTH", "").strip()
        candidates.append(f"{base}, SOUTH")
    if normalized.endswith(" NORTH"):
        base = normalized.replace(" NORTH", "").strip()
        candidates.append(f"{base}, NORTH")
    # Remove duplicates and skip identical form.
    uniq: List[str] = []
    seen: set[str] = set()
    for c in candidates:
        cu = c.upper()
        if cu == raw_name.upper() or cu in seen:
            continue
        seen.add(cu)
        uniq.append(c)
    return uniq


def load_country_code_map(csv_path: str) -> Dict[str, str]:
    """
    Load country-name -> CTY_CODE map from local reference CSV.

    This cache lets us resolve country names without an extra API discovery call.
    """
    expanded = os.path.expanduser(csv_path)
    if not os.path.exists(expanded):
        return {}

    out: Dict[str, str] = {}
    try:
        with open(expanded, "r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                code = str(row.get("CTY_CODE", "")).strip()
                if not is_country_code(code):
                    continue
                raw_name = str(row.get("CTY_NAME", "")).strip()
                norm_name = str(row.get("CTY_NAME_NORM", "")).strip()
                if raw_name:
                    out[normalize_country_name(raw_name)] = code
                if norm_name:
                    out[normalize_country_name(norm_name)] = code
    except OSError:
        return {}
    return out


def resolve_country_code_from_cache(raw_name: str, code_map: Dict[str, str]) -> str:
    """Resolve CTY_CODE from local cache using normalized names and aliases."""
    if not raw_name or not code_map:
        return ""
    normalized = normalize_country_name(raw_name)
    if normalized in code_map:
        return code_map[normalized]

    alias = COUNTRY_NAME_ALIASES.get(normalized)
    if alias:
        alias_norm = normalize_country_name(alias)
        if alias_norm in code_map:
            return code_map[alias_norm]
    return ""


def fetch_json(url: str) -> List[List[str]]:
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=60) as response:
        payload = response.read().decode("utf-8")
    if not payload.strip():
        return []
    return json.loads(payload)


def normalize_rows(raw_rows: List[List[str]]) -> List[List[str]]:
    """Drop duplicate header columns returned by Census (e.g., YEAR repeated)."""
    if not raw_rows:
        return []
    headers = raw_rows[0]
    keep_indexes: List[int] = []
    seen: set[str] = set()
    for idx, name in enumerate(headers):
        if name in seen:
            continue
        seen.add(name)
        keep_indexes.append(idx)

    normalized: List[List[str]] = []
    normalized.append([headers[idx] for idx in keep_indexes])
    for row in raw_rows[1:]:
        normalized.append([row[idx] if idx < len(row) else "" for idx in keep_indexes])
    return normalized


def aggregate_rows(
    rows: List[List[str]], group_fields: List[str], sum_field: str
) -> List[List[str]]:
    if not rows or len(rows) == 1:
        return rows

    headers = rows[0]
    if sum_field not in headers:
        raise ValueError(f"--sum-field '{sum_field}' not found in response columns.")
    missing = [field for field in group_fields if field not in headers]
    if missing:
        raise ValueError(f"--group-by field(s) not found in response: {', '.join(missing)}")

    idx = {name: i for i, name in enumerate(headers)}
    groups: Dict[Tuple[str, ...], int] = {}
    for row in rows[1:]:
        key = tuple(row[idx[field]] for field in group_fields)
        raw_value = row[idx[sum_field]].replace(",", "")
        try:
            value = int(float(raw_value))
        except ValueError:
            value = 0
        groups[key] = groups.get(key, 0) + value

    out_headers = group_fields + [sum_field]
    out_rows: List[List[str]] = [out_headers]
    for key in sorted(groups.keys()):
        out_rows.append(list(key) + [str(groups[key])])
    return out_rows


def is_country_code(code: str) -> bool:
    """Return True for 4-digit numeric country codes (exclude blocs/regions)."""
    return isinstance(code, str) and code.isdigit() and int(code) >= 1000


def filter_country_only(rows: List[List[str]]) -> List[List[str]]:
    if not rows or len(rows) == 1:
        return rows
    headers = rows[0]
    if "CTY_CODE" not in headers:
        raise ValueError("CTY_CODE column is required for --country-only.")
    cty_idx = headers.index("CTY_CODE")
    filtered = [headers]
    for row in rows[1:]:
        code = row[cty_idx] if cty_idx < len(row) else ""
        if is_country_code(code):
            filtered.append(row)
    return filtered


def fill_missing_months(rows: List[List[str]], sum_field: str) -> List[List[str]]:
    """Fill missing YEAR/MONTH combinations with zero for the sum_field."""
    if not rows or len(rows) == 1:
        return rows
    headers = rows[0]
    required = {"YEAR", "MONTH", sum_field}
    if not required.issubset(set(headers)):
        missing = ", ".join(sorted(required - set(headers)))
        raise ValueError(f"Cannot --fill-months, missing column(s): {missing}")

    idx = {name: i for i, name in enumerate(headers)}
    existing: Dict[Tuple[str, str], str] = {}
    years: set[str] = set()

    for row in rows[1:]:
        year = str(row[idx["YEAR"]])
        month = str(row[idx["MONTH"]]).zfill(2)
        years.add(year)
        val = str(row[idx[sum_field]])
        existing[(year, month)] = val

    out = [headers]
    for year in sorted(years):
        for m in range(1, 13):
            month = f"{m:02d}"
            row = [""] * len(headers)
            row[idx["YEAR"]] = year
            row[idx["MONTH"]] = month
            row[idx[sum_field]] = existing.get((year, month), "0")
            out.append(row)
    return out


def print_table(rows: List[List[str]]) -> None:
    if not rows:
        print("No rows returned (endpoint may have returned no-data/204 for this filter set).")
        return
    if len(rows) == 1:
        print("Headers only. No data rows returned.")
        print(", ".join(rows[0]))
        return

    headers = rows[0]
    data = rows[1:]

    widths = [len(h) for h in headers]
    for row in data:
        for i, value in enumerate(row):
            if i < len(widths):
                widths[i] = max(widths[i], len(str(value)))

    header_line = " | ".join(h.ljust(widths[i]) for i, h in enumerate(headers))
    sep_line = "-+-".join("-" * widths[i] for i in range(len(headers)))
    print(header_line)
    print(sep_line)
    for row in data:
        print(" | ".join(str(row[i]).ljust(widths[i]) for i in range(len(headers))))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Query Census International Trade API with HS scope confirmation."
    )
    parser.add_argument(
        "--path",
        required=True,
        help="Endpoint path under /data/timeseries/intltrade, e.g. imports/enduse.",
    )
    parser.add_argument(
        "--param",
        action="append",
        default=[],
        help="Query param in KEY=VALUE format. Repeat for multiple params.",
    )
    parser.add_argument(
        "--hs-codes",
        default="",
        help="Comma/space separated HS codes. Example: '85,8528,852872'.",
    )
    parser.add_argument(
        "--hs-code-param",
        default="",
        help="Parameter name used by endpoint for HS code filter, e.g. COMMCODE.",
    )
    parser.add_argument(
        "--confirm-scope",
        action="store_true",
        help="Required when --hs-codes is provided. Confirms scope before execution.",
    )
    parser.add_argument(
        "--api-key",
        default="",
        help="Optional API key override. Defaults to CENSUS_API_KEY env var.",
    )
    parser.add_argument(
        "--group-by",
        default="",
        help="Comma-separated fields for aggregation (e.g. YEAR,MONTH).",
    )
    parser.add_argument(
        "--sum-field",
        default="",
        help="Numeric field to sum when --group-by is used (e.g. GEN_VAL_MO).",
    )
    parser.add_argument(
        "--hs-chunk-size",
        type=int,
        default=50,
        help="Max HS codes per request when --hs-codes is provided.",
    )
    parser.add_argument(
        "--country-only",
        action="store_true",
        help="Keep only 4-digit numeric country rows (drop regional aggregates).",
    )
    parser.add_argument(
        "--fill-months",
        action="store_true",
        help="After aggregation, fill missing YEAR/MONTH rows with 0 values.",
    )
    parser.add_argument(
        "--country-code-file",
        default="",
        help=(
            "Optional CSV mapping for country names to CTY_CODE. "
            "Defaults to references/country_codes.csv in this skill."
        ),
    )
    args = parser.parse_args()

    api_key = args.api_key or os.getenv("CENSUS_API_KEY") or load_api_key_from_codex_env()
    if not api_key:
        raise SystemExit(
            "Missing API key. Set CENSUS_API_KEY, put it in ~/.codex/census.env, "
            "or provide --api-key for this run."
        )

    if args.hs_chunk_size <= 0:
        raise SystemExit("--hs-chunk-size must be >= 1.")

    params = parse_key_value(args.param)
    country_code_file = (
        args.country_code_file.strip() if args.country_code_file.strip() else str(DEFAULT_COUNTRY_CODES_PATH)
    )
    country_code_map = load_country_code_map(country_code_file)

    if "CTY_CODE" not in params and isinstance(params.get("CTY_NAME"), str):
        requested_name = str(params["CTY_NAME"])
        resolved_code = resolve_country_code_from_cache(requested_name, country_code_map)
        if resolved_code:
            params["CTY_CODE"] = resolved_code
            del params["CTY_NAME"]
            print(f"Country resolved from local cache: {requested_name} -> {resolved_code}")

    hs_codes = parse_hs_codes(args.hs_codes) if args.hs_codes else []

    request_urls: List[str] = []
    rows: List[List[str]] = []

    # Keep multi-year pulls in one API request when possible.
    # - YEAR range (2016-2025) => time=from 2016-.. to 2025-..
    # - YEAR list (2024,2025) => repeated YEAR params
    if "time" not in params and isinstance(params.get("YEAR"), str):
        raw_year = str(params["YEAR"]).strip()
        parsed_range = parse_year_range(raw_year)
        if parsed_range:
            month_bounds = month_bounds_for_time(params.get("MONTH"))
            if month_bounds:
                start_year, end_year = parsed_range
                start_month, end_month = month_bounds
                params["time"] = (
                    f"from {start_year:04d}-{start_month} to {end_year:04d}-{end_month}"
                )
                del params["YEAR"]
            else:
                params["YEAR"] = [str(y) for y in range(parsed_range[0], parsed_range[1] + 1)]
        else:
            parsed_years = parse_year_values(raw_year)
            if len(parsed_years) > 1:
                params["YEAR"] = parsed_years
            elif len(parsed_years) == 1 and parsed_years[0] != raw_year:
                params["YEAR"] = parsed_years[0]

    if hs_codes:
        if not args.hs_code_param:
            raise SystemExit(
                "You provided --hs-codes but not --hs-code-param. "
                "Set the endpoint's HS field name before running."
            )
        if not args.confirm_scope:
            raise SystemExit(
                "HS scope not confirmed. Re-run with --confirm-scope after reviewing "
                f"codes: {', '.join(hs_codes)}"
            )
        # Use repeated query params for HS codes (e.g. I_COMMODITY=...&I_COMMODITY=...),
        # which works reliably on this API, unlike comma-separated values.
        for start in range(0, len(hs_codes), args.hs_chunk_size):
            chunk = hs_codes[start : start + args.hs_chunk_size]
            scoped = dict(params)
            scoped[args.hs_code_param] = chunk
            url = build_url(args.path, scoped, api_key)
            request_urls.append(url)
            try:
                raw = fetch_json(url)
            except Exception as exc:  # pragma: no cover - runtime network path
                raise SystemExit(
                    f"API request failed for HS chunk ({len(chunk)} codes): {exc}"
                ) from exc
            normalized = normalize_rows(raw)
            if not normalized:
                continue
            if not rows:
                rows = normalized
            else:
                rows.extend(normalized[1:])
    else:
        scoped = dict(params)

        url = build_url(args.path, scoped, api_key)
        request_urls.append(url)
        try:
            normalized = normalize_rows(fetch_json(url))
        except Exception as exc:  # pragma: no cover - runtime network path
            raise SystemExit(f"API request failed: {exc}") from exc

        # If name-based query returns empty, try alias fallbacks automatically.
        if (not normalized or len(normalized) <= 1) and isinstance(scoped.get("CTY_NAME"), str):
            for candidate in country_retry_candidates(str(scoped["CTY_NAME"])):
                retry_params = dict(scoped)
                retry_params["CTY_NAME"] = candidate
                retry_url = build_url(args.path, retry_params, api_key)
                request_urls.append(retry_url)
                try:
                    retry_rows = normalize_rows(fetch_json(retry_url))
                except Exception:
                    retry_rows = []
                if retry_rows and len(retry_rows) > 1:
                    normalized = retry_rows
                    break

        if normalized:
            rows = normalized

    for idx, url in enumerate(request_urls, start=1):
        prefix = f"Request URL {idx}" if len(request_urls) > 1 else "Request URL"
        print(f"{prefix}: {redact_key(url)}")

    if args.group_by:
        if not args.sum_field:
            raise SystemExit("--sum-field is required when using --group-by.")
        group_fields = [item.strip() for item in args.group_by.split(",") if item.strip()]
        rows = aggregate_rows(rows, group_fields, args.sum_field)
        if args.fill_months:
            rows = fill_missing_months(rows, args.sum_field)
    elif args.fill_months:
        raise SystemExit("--fill-months requires --group-by and --sum-field.")

    if args.country_only:
        rows = filter_country_only(rows)

    print_table(rows)


if __name__ == "__main__":
    try:
        main()
    except ValueError as exc:
        print(f"Input error: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
