---
name: census-intl-trade-hs
description: Use this skill for U.S. international trade questions using the Census International Trade API, especially when prompts include HS codes or product names that must be mapped to HS code scope with explicit user confirmation before querying.
---

# Census International Trade (HS Scoped)

Use this skill when a user asks for U.S. imports/exports from the Census International Trade API and the request involves HS codes or product keywords.

## What this skill enforces

1. Always confirm HS scope before running a data query.
2. If a user provides HS codes directly, treat those as source-of-truth input.
3. Never silently choose one HS branch for ambiguous product prompts.
4. Always include an explicit `get=` field list in API requests.
5. Prefer `CTY_CODE` over `CTY_NAME` for final value pulls.
6. Always show the exact API endpoint URL(s) used with no API key in the shared URL.
7. Do not save or attach CSV files unless the user explicitly asks for CSV/file output.

## Workflow

1. Parse request into slots:
- `flow`: imports or exports
- `time`: monthly or annual period
- `geography`: partner/country if present
- `hs_input`: explicit HS code(s), ranges, or product keyword
- `metric`: value/quantity if specified

Flow interpretation rule (required):
- If user says "exports to the US" or "exports into the US", interpret as **U.S. imports** (`imports/hs`).
- If user says "imports from the US", interpret as **U.S. exports** (`exports/hs`).
- If direction is ambiguous, ask one clarification question before querying.
- Once confirmed, keep the chosen direction for the rest of the thread unless the user explicitly changes it.

2. Resolve HS scope:
- If explicit code(s) are present, normalize to digits and preserve user intent.
- If no explicit codes are present, propose likely HS candidates and ask one clarifying question.

3. Resolve country identifier (if country is provided):
- First check local reference file `references/country_codes.csv` for `CTY_CODE`.
- If not found in the local file, resolve `CTY_NAME` to `CTY_CODE` via API discovery.
- If a name-based pull returns empty/204, retry with resolved `CTY_CODE`.

4. Confirm scope before query:
- Show level(s): `2/4/6/8`
- Show mode: `exact` or `expanded`
- Show final code list (or count + list pointer when long)
- Ask for explicit confirmation.

5. Query Census API only after confirmation.
- Include explicit `get=` fields in every request.
- For category ranking requests, confirm HS level (`2/4/6/8`) before querying.
- If HS level is not specified after one clarification, default to HS2 and state that default.

6. Return:
- summary of what was pulled (one short paragraph)
- inline data table (if large, show a preview and note that CSV is available on request)
- CSV download option only when explicitly requested by the user
- API endpoint URL(s) used for the pull, without API key query params
- scope note with HS codes included
- note on annual semantics when `GEN_VAL_YR`/`ALL_VAL_YR` is used (`MONTH=12` year-to-date total)

Data response format (required when user asked for data):
1. `Summary of what you pulled`
2. `Inline table with data` (or `table preview shown; CSV available on request` when large)
3. `API endpoint(s) used` (no `key=` param shown)
4. `CSV download` (file name + attachment/link) only if user explicitly requested CSV/file output

## Internal AI checklist (required)

Use this checklist internally before any share/percent calculation query. Do not print this full checklist to the user.

1. Confirm direction mapping:
- "to the US" => `imports/*`
- "from the US" => `exports/*`
- persist this mapping for subsequent turns until explicitly changed by the user

2. Confirm measure:
- annual: `GEN_VAL_YR` or `CON_VAL_YR`
- monthly: matching `_MO` field

3. Confirm time basis:
- annual totals must use `MONTH=12` and yearly measure fields
- time range must be explicit

4. Confirm denominator:
- use world total row, not summed countries:
  - imports: `CTY_CODE=-` and `I_COMMODITY=-`
  - exports: `CTY_CODE=-` and `E_COMMODITY=-`

5. Confirm country scope:
- fixed country list or dynamic top-N per year
- if top-N, confirm ranking rule (re-rank each year vs lock the top-N from a baseline year)

6. Confirm identifiers:
- resolve `CTY_NAME` to `CTY_CODE` using local reference first, then API fallback
- prefer code-based queries in final requests
- if a name-based query returns empty/204, retry using resolved `CTY_CODE`

7. Confirm commodity scope:
- total row (`-`) vs HS list
- if HS list, confirm exact/expanded mode and final list

8. Confirm no-data handling:
- treat empty/204 as no-data, not success
- retry using safer parameter style if relevant

9. Confirm response parsing:
- de-duplicate repeated API columns (e.g., `YEAR`, `MONTH`, code fields) before computing metrics

10. Confirm calculation policy:
- compute percentages from raw values
- round only final display values

11. Confirm output schema:
- columns and units are explicit
- difference columns include sign convention if requested

12. Confirm ranking inputs:
- for top-N country calculations, filter to country rows only (exclude blocs/regions)
- use 4-digit numeric country codes (`CTY_CODE >= 1000`) for ranking

13. Confirm multi-year execution:
- do not pass comma-separated `YEAR` values in one API call
- prefer one API call for multi-year pulls:
  - contiguous ranges: use `time=from+YYYY-MM+to+YYYY-MM` (keep `MONTH` filter when needed)
  - non-contiguous years: repeat `YEAR` predicates (`...&YEAR=2022&YEAR=2024`)
- only fall back to one-request-per-year if the endpoint returns no data for the single-call pattern

14. Confirm API select list:
- include explicit `get=` fields on every request
- include only fields needed for the calculation

15. Confirm category-ranking level:
- if user asks for "largest category" and does not specify level, ask HS level (`2/4/6/8`)
- if user does not choose after one clarification, default to HS2 and state it

16. Confirm hierarchy handling for wildcard commodity pulls:
- when using `I_COMMODITY=*` or `E_COMMODITY=*`, filter to exactly one HS level before ranking
- do not mix chapter/heading/subheading values in the same rank calculation

## User preflight (short form)

Before running ambiguous requests, ask only what is necessary:

1. Direction: "Just confirming: do you mean U.S. imports (to the US) or U.S. exports (from the US)?"
2. Scope: "Use all commodities (total row) or specific HS codes?"
3. Country logic: "Use your fixed country list or top-N countries each year?"
4. Category level (for ranking prompts): "For category ranking, use HS2, HS4, HS6, or HS8?"
5. Measure/rounding (if unspecified): "Use general customs value and round to how many decimals?"

## Proven query patterns

Use these patterns by default unless the user requests otherwise.

General rule for all patterns:
- always include an explicit `get=` field list in every API request

1. Country total exports/imports (all commodities):
- endpoint: `exports/hs` or `imports/hs`
- predicates: commodity code set to total row (`E_COMMODITY=-` or `I_COMMODITY=-`)
- annual total: `MONTH=12` with `ALL_VAL_YR`/`GEN_VAL_YR`
- country filter: prefer `CTY_CODE`; use `CTY_NAME` only for discovery, then switch to code

Direction mapping quick reference:
- "to the US" => `imports/hs`
- "from the US" => `exports/hs`
- "US imports from X" => `imports/hs`
- "US exports to X" => `exports/hs`

2. HS-scoped trade pulls:
- send HS filters as repeated params, not comma-separated:
  - good: `...&I_COMMODITY=852872&I_COMMODITY=852873`
  - risky: `...&I_COMMODITY=852872,852873` (may return empty/204)

3. Country selector:
- prefer `CTY_CODE` once known (stable)
- for common country names, use `references/country_codes.csv` first
- accept `CTY_NAME` during discovery only when local reference has no match, then convert to code
- when computing top-N country rankings, exclude non-country aggregates and blocs

4. Top category by year (HS level-aware):
- query yearly values with `get=<commodity_code>,<commodity_desc>,<yearly_value_field>`
- for annual totals use `MONTH=12` and yearly value field (`GEN_VAL_YR`/`ALL_VAL_YR`)
- if querying all commodities (`*`), filter to one HS level (2/4/6/8) before ranking
- pick max category per year after level filtering

5. Multi-year time filters:
- contiguous spans: prefer `time=from+YYYY-MM+to+YYYY-MM`
- non-contiguous years: use repeated `YEAR` params
- avoid `YEAR=2024,2025` (can return empty/204)

## Scope confirmation template

Use this exact structure before any API request:

`HS scope check`
- `Codes parsed`: ...
- `Level`: ...
- `Mode`: `exact` or `expanded to descendants`
- `Final code set`: ...
- `Proceed?`: yes/no

If user says no, revise scope and repeat.

## Script usage

This skill includes a helper script:

- query_trade_api.py
- build_country_codes_reference.py

The script enforces a scope confirmation gate with `--confirm-scope` so accidental ambiguous runs are blocked.

Example:

```bash
uv run --with pandas -- python query_trade_api.py \
  --path imports/hs \
  --param YEAR=2025 \
  --param 'MONTH=*' \
  --param CTY_CODE=5700 \
  --hs-codes 852872,852873 \
  --hs-code-param I_COMMODITY \
  --confirm-scope \
  --group-by YEAR,MONTH \
  --sum-field GEN_VAL_MO \
  --fill-months
```

Implementation note:
- The script sends HS filters as repeated params (`...&I_COMMODITY=852872&I_COMMODITY=852873`) rather than comma-separated values, because this has proven more reliable for the Census trade endpoint.
- Quote wildcard params in shell commands (for example `--param 'I_COMMODITY=*'`) so the shell does not expand `*` before the request.
- The script can return empty output for `204`-style no-data responses. Treat this as a data miss and revise filters.
- Use `--country-only` when ranking countries to drop regional/treaty aggregates.
- Use `--fill-months` with grouped monthly outputs to add zero rows for missing months.
- The script keeps multi-year pulls in one request when possible:
  - `YEAR=2016-2025` is converted to a `time=from ... to ...` predicate
  - `YEAR=2024,2025` is sent as repeated `YEAR` params in one call
- The script auto-retries common country-name aliases (for example `SOUTH KOREA` -> `KOREA, SOUTH`) when name-based queries return empty.
- The script auto-resolves `CTY_NAME` to `CTY_CODE` from `references/country_codes.csv` before making API calls.
- API key lookup order is: `--api-key`, then `CENSUS_API_KEY` env, then `~/.codex/census.env`.

Country code reference note:
- Local cache file: `references/country_codes.csv`
- Use this file first to map country names to `CTY_CODE` and avoid extra discovery calls.
- Refresh with:
  `uv run --with pandas -- python scripts/build_country_codes_reference.py`

## References

- Endpoint map: [endpoints.md](references/endpoints.md)
- HS scope rules: [hs_scope.md](references/hs_scope.md)
- Country code cache: [country_codes.csv](references/country_codes.csv)
