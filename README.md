# census-intl-trade-hs

Skill and helper scripts for querying the U.S. Census International Trade API with HS-code scope checks.

This is very much under development and **not 100 percent reliable**! Always check important information returned by an LLM. Please give feedback with examples you've used via `Discussions` or `Issues` tabs.

## What this repo includes

- `SKILL.md`: prompt rules and workflow for HS-scoped trade analysis.
- `scripts/query_trade_api.py`: CLI for Census trade API pulls with guardrails.
- `scripts/build_country_codes_reference.py`: refreshes local country code cache.
- `references/`: endpoint notes, HS scope notes, and country code reference CSV.
- `agents/openai.yaml`: optional agent metadata.

## Prerequisites

- `uv` installed.
  - Install: `curl -LsSf https://astral.sh/uv/install.sh | sh`
- A Census API key.

## Install as a Codex skill

Clone this repo, then copy it into your Codex skills directory with the same folder name:

```bash
mkdir -p ~/.codex/skills
rsync -av /path/to/census-intl-trade-hs/ ~/.codex/skills/census-intl-trade-hs/
```

Use it in prompts with:

```text
Use $census-intl-trade-hs to answer this trade question...
```

## Using with Claude Code

Use this implementation flow for Claude Code.

### 1) Install in Claude

1. Download this repo (`git clone` or ZIP from GitHub).
2. In Claude, open `Settings -> Skills`.
3. Click `Upload skill` and select the skill folder (zip if prompted).

### 2) Enable and verify runtime access

- Enable the uploaded skill in Claude.
- If your setup uses MCP tools, confirm the MCP server is connected.
- Set your API key in the shell used for script execution:

```bash
export CENSUS_API_KEY='your_key_here'
```

To persist it, add that line to your shell profile (`~/.zshrc`, `~/.bashrc`, etc.).

### 3) Test with a real query

```
Use the census-intl-trade-hs skill workflow in SKILL.md to get total imports from China in the last few years.
```

## Give the skill access to your Census API key

The script checks for an API key in this order:
1. `--api-key` argument (one run only)
2. `CENSUS_API_KEY` environment variable
3. `~/.codex/census.env`

### Option 1: Environment variable (recommended)

```bash
export CENSUS_API_KEY='your_key_here'
```

To persist it, add that line to your shell profile (`~/.zshrc`, `~/.bashrc`, etc.).

### Option 2: Codex env file

```bash
mkdir -p ~/.codex
cat > ~/.codex/census.env <<'EOF2'
CENSUS_API_KEY=your_key_here
EOF2
chmod 600 ~/.codex/census.env
```

## Natural-language query examples

- "For Brazil, give monthly U.S. imports in 2024 for HS code 0901."
- "What were the top 10 source countries for U.S. imports in 2025?"
- "Compare U.S. exports to Canada vs. Mexico for 2021 through 2025."
- "For U.S. imports from China, find the largest HS2 category each year since 2018."
- "Give U.S. exports to Germany for computers."