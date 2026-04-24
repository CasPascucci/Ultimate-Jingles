#!/usr/bin/env python3
"""
fill_regex.py — Finds entries in index.json that are missing a "regex" field
and uses the Claude API to generate well-crafted Cocoon Shell regex patterns.

Can also normalize poorly-named entries (abbreviations, shorthands, etc.) and
split them into multiple properly-named entries when needed.

Usage:
    python scripts/fill_regex.py [--index PATH] [--dry-run] [--no-fix-names]

Environment:
    ANTHROPIC_API_KEY   Required. Your Anthropic API key.
"""

import argparse
import json
import os
import sys
from pathlib import Path

import anthropic

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).parent.parent
DEFAULT_INDEX = REPO_ROOT / "index.json"
RULES_FILE = Path(__file__).parent / "regex_rules.md"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def load_index(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_index(data: dict, path: Path) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")


def find_missing(data: dict) -> list[tuple[str, int, dict]]:
    """Return (platform, index, entry) for every entry missing a 'regex' key."""
    missing = []
    for key, value in data.items():
        if not isinstance(value, list):
            continue  # skip top-level non-list fields like "name"
        for i, entry in enumerate(value):
            if isinstance(entry, dict) and "regex" not in entry:
                missing.append((key, i, entry))
    return missing


def load_rules() -> str:
    if not RULES_FILE.exists():
        sys.exit(f"ERROR: Rules file not found at {RULES_FILE}")
    return RULES_FILE.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Claude API call
# ---------------------------------------------------------------------------

def generate_regex(missing: list[tuple[str, int, dict]], rules: str, client: anthropic.Anthropic) -> list[dict]:
    """
    Ask Claude to generate regex patterns for the given entries.
    Returns a list of {"platform": ..., "name": ..., "regex": ...} dicts.
    """
    needs_patterns = [
        {"platform": platform, "name": entry["name"]}
        for platform, _, entry in missing
    ]

    system = (
        "You are a regex pattern generator for the Cocoon Shell jingle matching system.\n"
        "You will be given a list of game entries that need regex patterns.\n"
        "Apply every rule in the provided rules document carefully.\n\n"
        "IMPORTANT: Respond with ONLY a valid JSON array. "
        "No markdown fences, no preamble, no explanation. "
        "Each element must have exactly three keys: platform, name, regex."
    )

    user = (
        f"Rules document:\n\n{rules}\n\n"
        "---\n\n"
        "Generate regex patterns for every entry in this list:\n\n"
        f"{json.dumps(needs_patterns, indent=2)}"
    )

    print(f"  Calling Claude API for {len(needs_patterns)} entries...")
    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=4096,
        system=system,
        messages=[{"role": "user", "content": user}],
    )

    raw = message.content[0].text.strip()

    # Strip accidental markdown fences
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1]
        raw = raw.rsplit("```", 1)[0].strip()

    try:
        results = json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"ERROR: Claude returned non-JSON output:\n{raw}")
        sys.exit(f"JSON parse error: {e}")

    if not isinstance(results, list):
        sys.exit(f"ERROR: Expected a JSON array from Claude, got: {type(results)}")

    return results


# ---------------------------------------------------------------------------
# Name normalisation
# ---------------------------------------------------------------------------

def normalize_names(data: dict, client: anthropic.Anthropic) -> tuple[dict, int]:
    """
    Scan all entries for poorly-named games (abbreviations, shorthands, initialism-
    only names) and fix them — renaming in place or splitting into multiple entries.

    Returns the updated data dict and a count of how many entries were changed.
    """

    # Collect every entry for Claude to review
    candidates = []
    for key, value in data.items():
        if not isinstance(value, list):
            continue
        for i, entry in enumerate(value):
            if isinstance(entry, dict) and "name" in entry:
                candidates.append({"platform": key, "index": i, "name": entry["name"]})

    if not candidates:
        return data, 0

    system = (
        "You are a video game catalogue quality reviewer.\n"
        "You will receive a list of jingle index entries. For each entry, decide "
        "whether its 'name' field is a properly expanded game title, or needs to be "
        "fixed or split.\n\n"
        "Flag an entry for replacement if ANY of these are true:\n"
        "  - It is a pure initialism or abbreviation (e.g. 'Pokemon dp', 'NSMB2', "
        "'MK7', 'ffx', 'botw')\n"
        "  - It names two or more distinct retail games in one entry — this ALWAYS "
        "requires a split, regardless of how the name is phrased. "
        "'Pokemon Diamond and Pearl', 'Pokemon dp', 'HeartGold SoulSilver', "
        "'Pokemon HeartGold and SoulSilver' — all of these must be split into "
        "separate entries, one per game.\n"
        "  - It is truncated and missing a subtitle or key word that is part of the "
        "official title\n"
        "  - It is insider shorthand that a normal player would not recognise "
        "(e.g. 'Pikmin NPC' instead of 'Pikmin New Play Control')\n\n"
        "The ONLY time two game titles belong in one entry is if they were released "
        "as a single combined product with its own distinct title "
        "(e.g. 'Super Mario Bros. / Duck Hunt' on a multicart — keep that as-is).\n\n"
        "For each entry return EXACTLY ONE of:\n"
        "  {\"platform\": ..., \"index\": ..., \"action\": \"keep\"}\n"
        "  {\"platform\": ..., \"index\": ..., \"action\": \"replace\", "
        "\"entries\": [{\"name\": \"Full Official Title\"}, ...]}\n\n"
        "Rules for 'replace':\n"
        "  - Use the full, official retail title exactly as it appears on the box "
        "/ Wikipedia.\n"
        "  - For splits, return one entry object per game. The caller assigns the "
        "same jingle file to all of them automatically.\n"
        "  - Do NOT change entries that are already correct.\n\n"
        "IMPORTANT: Respond with ONLY a valid JSON array. "
        "No markdown fences, no preamble, no explanation."
    )

    user = (
        "Review every entry below and return your action for each one:\n\n"
        f"{json.dumps(candidates, indent=2)}"
    )

    print(f"  Calling Claude API to review {len(candidates)} entries for naming quality...")
    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4096,
        system=system,
        messages=[{"role": "user", "content": user}],
    )

    raw = message.content[0].text.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1]
        raw = raw.rsplit("```", 1)[0].strip()

    try:
        decisions = json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"ERROR: Claude returned non-JSON output:\n{raw}")
        sys.exit(f"JSON parse error: {e}")

    if not isinstance(decisions, list):
        sys.exit(f"ERROR: Expected a JSON array from Claude, got: {type(decisions)}")

    # Apply decisions in reverse-index order so insertions don't shift indices
    replace_decisions = [d for d in decisions if d.get("action") == "replace"]
    # Sort by index descending so we can splice safely
    replace_decisions.sort(key=lambda d: d["index"], reverse=True)

    changed = 0
    for decision in replace_decisions:
        platform = decision["platform"]
        idx = decision["index"]
        new_entries_spec = decision.get("entries", [])

        if not new_entries_spec or not isinstance(data.get(platform), list):
            continue

        original_entry = data[platform][idx]
        original_file = original_entry.get("file", "")
        original_name = original_entry.get("name", "")

        # Build replacement entries — inherit file, drop regex so fill pass regenerates
        replacements = []
        for spec in new_entries_spec:
            new_entry = {"name": spec["name"], "file": original_file}
            # Preserve any other fields from original except name/regex
            for k, v in original_entry.items():
                if k not in ("name", "file", "regex"):
                    new_entry[k] = v
            replacements.append(new_entry)

        # Splice: remove old entry, insert replacements at same position
        data[platform] = (
            data[platform][:idx]
            + replacements
            + data[platform][idx + 1:]
        )

        if len(replacements) == 1:
            print(f"  ✎ [{platform}] '{original_name}' → '{replacements[0]['name']}'")
        else:
            print(f"  ✎ [{platform}] '{original_name}' → split into {len(replacements)} entries:")
            for r in replacements:
                print(f"      • {r['name']}")
        changed += 1

    return data, changed


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Fill missing regex fields in index.json")
    parser.add_argument("--index", type=Path, default=DEFAULT_INDEX,
                        help="Path to index.json (default: repo root)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print what would change without writing the file")
    parser.add_argument("--no-fix-names", action="store_true",
                        help="Skip name normalisation and only fill missing regex fields")
    args = parser.parse_args()

    if not args.index.exists():
        sys.exit(f"ERROR: index.json not found at {args.index}")

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        sys.exit("ERROR: ANTHROPIC_API_KEY environment variable is not set.")

    client = anthropic.Anthropic(api_key=api_key)

    print(f"Loading {args.index} ...")
    data = load_index(args.index)

    # ── Pass 1: name normalisation (on by default) ───────────────────────────
    name_changes = 0
    if not args.no_fix_names:
        print("\n── Name normalisation pass ──────────────────────────────────────")
        data, name_changes = normalize_names(data, client)
        if name_changes == 0:
            print("  ✓ All entry names look good. Nothing to fix.")
        else:
            print(f"  {name_changes} entry/entries updated.")

    # ── Pass 2: regex fill ───────────────────────────────────────────────────
    print("\n── Regex fill pass ─────────────────────────────────────────────────")
    missing = find_missing(data)

    if not missing:
        print("✓ All entries already have regex fields. Nothing to do.")
        if args.dry_run or name_changes == 0:
            return
    else:
        print(f"Found {len(missing)} entr{'y' if len(missing) == 1 else 'ies'} missing regex:")
        for platform, _, entry in missing:
            print(f"  [{platform}] {entry['name']}")
        print()

        rules = load_rules()
        results = generate_regex(missing, rules, client)

        # Build lookup: (platform, name) -> regex
        lookup: dict[tuple[str, str], str] = {
            (r["platform"], r["name"]): r["regex"]
            for r in results
            if "platform" in r and "name" in r and "regex" in r
        }

        filled = 0
        warnings = []

        for platform, idx, entry in missing:
            key = (platform, entry["name"])
            if key in lookup:
                if not args.dry_run:
                    data[platform][idx]["regex"] = lookup[key]
                print(f"  ✓ [{platform}] {entry['name']}")
                print(f"      → {lookup[key]}")
                filled += 1
            else:
                warnings.append(f"  ⚠ No pattern returned for [{platform}] {entry['name']}")

        for w in warnings:
            print(w)

        if args.dry_run:
            print(f"\nDry run complete — {filled} pattern(s) would be written.")
            if not args.no_fix_names:
                print(f"  (name normalisation: {name_changes} change(s) would be applied)")
            return

        if warnings:
            print(f"\n⚠ {len(warnings)} entry/entries could not be filled (see above).")

    # ── Write output ─────────────────────────────────────────────────────────
    if not args.dry_run:
        save_index(data, args.index)
        parts = []
        if missing:
            parts.append(f"{filled} new regex field(s) added")
        if name_changes:
            parts.append(f"{name_changes} name(s) normalised")
        print(f"\n✓ Saved {args.index} — {', '.join(parts)}.")

        if missing and warnings:
            sys.exit(1)  # Non-zero exit so CI can flag it


if __name__ == "__main__":
    main()
