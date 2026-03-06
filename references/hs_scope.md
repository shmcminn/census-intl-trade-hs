# HS Scope Rules

## Hierarchy

- HS2: chapter-level
- HS4: heading-level
- HS6: subheading-level
- HS8: detailed tariff-line style level used in some datasets

## Scope policy

1. If user provides HS code(s), parse and normalize digits only.
2. Allowed lengths are `2`, `4`, `6`, `8`; reject others and ask for correction.
3. Never auto-expand unless user explicitly approves expansion.
4. If keyword prompt (e.g., "TV imports"), propose candidate code families and require confirmation.

## Confirmation policy

Before query, show:
- parsed codes
- exact vs expanded mode
- final code set
- count of final codes

Then ask:
- "Proceed with this HS scope? (yes/no)"
