# Regex Automation Setup

This directory contains the GitHub Actions workflow and script that automatically
fill missing `regex` fields in `index.json` using Claude.

## How it works

1. **Schedule** — Runs every Monday at 06:00 UTC (or manually via Actions tab)
2. **Upstream sync** *(optional)* — If `UPSTREAM_URL` is set, merges changes from the upstream repo first
3. **Fill regex** — Calls the Claude API to generate patterns for any entries that lack a `regex` field. Existing patterns are never overwritten.
4. **Commit** — If anything changed, commits and pushes `index.json` back to the repo.

## One-time setup

### 1. Add your Anthropic API key

In your repo: **Settings → Secrets and variables → Actions → Secrets → New repository secret**

| Name | Value |
|---|---|
| `ANTHROPIC_API_KEY` | Your key from console.anthropic.com |

### 2. (Optional) Set an upstream URL

If this is a fork and you want to pull upstream changes automatically:

**Settings → Secrets and variables → Actions → Variables → New repository variable**

| Name | Value |
|---|---|
| `UPSTREAM_URL` | e.g. `https://github.com/someuser/original-jingle-repo` |

Leave this unset if you only want the regex-filling behaviour.

### 3. Allow Actions write access

**Settings → Actions → General → Workflow permissions** → select **Read and write permissions**

## Running manually

Go to **Actions → Sync Upstream & Fill Regex → Run workflow**.
Check "Dry run" to preview what would change without touching the file.

## Modifying the rules

Edit `scripts/regex_rules.md` — the rules are versioned in the repo and loaded
at runtime, so you never need to touch the Python script to adjust matching behaviour.
