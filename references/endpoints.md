# Census International Trade API Notes

Primary docs:
- https://www.census.gov/data/developers/data-sets/international-trade.html

Common base:
- `https://api.census.gov/data/timeseries/intltrade`

Common endpoint families:
- `imports/enduse`
- `exports/enduse`
- `imports/hs`
- `exports/hs`

Notes:
- Parameter names vary by endpoint family. Confirm accepted fields from the endpoint HTML docs before query execution.
- Keep API key in `CENSUS_API_KEY` and do not print raw keys in logs.
- For "latest" prompts, query the endpoint for newest available period and report exact month/year returned.
- Directionality mapping:
  - "exports to the US" means U.S. imports => use `imports/*` endpoints.
  - "imports from the US" means U.S. exports => use `exports/*` endpoints.
- For HS filters on `imports/hs` and `exports/hs`, prefer repeated params:
  - `...&I_COMMODITY=852872&I_COMMODITY=852873`
  - Avoid comma-separated HS lists, which may return empty (`204`) responses.
- For country totals across all commodities, use total commodity row:
  - exports: `E_COMMODITY=-`
  - imports: `I_COMMODITY=-`
  - annual: `MONTH=12` and `*_VAL_YR` measure fields
- Prefer `CTY_CODE` over `CTY_NAME` in final production queries for stability.
- For top-country rankings, exclude non-country aggregates/blocs and keep 4-digit numeric country codes only.
- For multi-year pulls, prefer a single request:
  - Contiguous ranges: use `time=from+YYYY-MM+to+YYYY-MM` (keep `MONTH` filter if needed).
  - Non-contiguous years: repeat the `YEAR` predicate (`...&YEAR=2022&YEAR=2024&YEAR=2025`).
  - Avoid comma-separated `YEAR` values (`YEAR=2024,2025`), which may return empty (`204`) responses.
