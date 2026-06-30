#!/usr/bin/env python3
"""
update-roster.py — merge tools (and CRM) mentioned in a Zoom transcript into members.json.

Usage:
    python update-roster.py <transcript.(txt|vtt)> [--members members.json] [--dry-run]

What it does:
  1. Parses a Zoom transcript (plain text or .vtt) into per-speaker utterances.
  2. Detects which TOOLS each speaker mentioned (any mention counts) and, if they
     named one of the known CRMs, which CRM.
  3. For speakers already in members.json: merges newly-found tools into their
     existing list, de-duplicated (case-insensitive). A detected CRM is only set if
     that member has no CRM yet — existing data is never overwritten.
  4. For speakers NOT in members.json: adds a new entry (name + tools + CRM),
     flagged "needsReview": true so you can verify it before trusting it.
  5. Writes members.json back (after backing up to members.json.bak) and prints a
     short diff summary. Use --dry-run to preview the summary and write nothing.

This extraction is deliberately heuristic and dependency-free so it runs standing
alone. The detection lives in extract_speaker_signals(); swap that one function for
an LLM-backed version later without touching the rest of the pipeline.
"""

import argparse
import datetime
import json
import os
import re
import sys

# --- Knowledge base ------------------------------------------------------------
# canonical tool name -> list of lowercase aliases to look for
TOOL_ALIASES = {
    "Claude": ["claude", "claude.ai", "anthropic", "claude code"],
    "ChatGPT": ["chatgpt", "chat gpt", "gpt-4", "gpt4", "openai"],
    "Suno.ai": ["suno", "suno.ai"],
    "Zoho CRM": ["zoho", "zoho crm"],
    "HubSpot": ["hubspot", "hub spot"],
    "17hats": ["17hats", "17 hats", "seventeen hats"],
    "Dubsado": ["dubsado"],
    "HoneyBook": ["honeybook", "honey book"],
    "Salesforce": ["salesforce"],
    "Pipedrive": ["pipedrive"],
    "Notion": ["notion"],
    "Airtable": ["airtable"],
    "Zapier": ["zapier"],
    "Make": ["make.com", "integromat"],
    "Canva": ["canva"],
    "Excel": ["excel", "spreadsheet"],
    "Google Sheets": ["google sheets", "gsheets"],
    "Midjourney": ["midjourney", "mid journey"],
    "ElevenLabs": ["elevenlabs", "eleven labs"],
    "Descript": ["descript"],
    "CapCut": ["capcut"],
}

# canonical CRM name -> lowercase aliases. The roster's `crm` field is a single
# choice from this set (plus a free-text "other"); detection only suggests one
# when a member has no CRM set yet.
CRM_ALIASES = {
    "17Hats": ["17hats", "17 hats", "seventeen hats"],
    "Mago": ["mago"],
    "HoneyBook": ["honeybook", "honey book"],
    "SpeakerFlow": ["speakerflow", "speaker flow"],
    "GHL": ["gohighlevel", "go high level", "highlevel", "ghl"],
}


# --- Transcript parsing --------------------------------------------------------
def parse_transcript(text):
    """Return list of (speaker, utterance_text). Handles .vtt and plain text."""
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    utterances = []
    current_speaker = None
    speaker_re = re.compile(r"^\s*([A-Z][\w.\-']*(?:\s+[A-Z][\w.\-']*){0,3})\s*(?:\([^)]*\))?\s*:\s*(.*)$")
    vtt_voice_re = re.compile(r"<v\s+([^>]+)>(.*?)</v>", re.IGNORECASE)
    ts_re = re.compile(r"^\s*(\d{1,2}:)?\d{1,2}:\d{2}[.,]\d{1,3}\s*-->")

    for raw in lines:
        line = raw.strip()
        if not line or line.upper().startswith("WEBVTT"):
            continue
        if ts_re.match(line) or line.isdigit():
            continue  # vtt timestamp or cue number
        # <v Speaker>text</v> form
        m = vtt_voice_re.search(line)
        if m:
            utterances.append((m.group(1).strip(), m.group(2).strip()))
            current_speaker = m.group(1).strip()
            continue
        # "Speaker Name: text" form
        m = speaker_re.match(line)
        if m and len(m.group(1)) <= 40:
            current_speaker = m.group(1).strip()
            if m.group(2).strip():
                utterances.append((current_speaker, m.group(2).strip()))
            continue
        # continuation line for the current speaker
        if current_speaker:
            utterances.append((current_speaker, line))
    return utterances


def aggregate_by_speaker(utterances):
    speakers = {}
    for speaker, text in utterances:
        speakers.setdefault(speaker, []).append(text)
    return {s: " ".join(parts) for s, parts in speakers.items()}


# --- Detection (swap this for an LLM call later) -------------------------------
def extract_speaker_signals(speaker_text):
    """Given one speaker's combined words, return (tools, crm_guess)."""
    low = " " + speaker_text.lower() + " "
    tools = [c for c, aliases in TOOL_ALIASES.items() if any(a in low for a in aliases)]
    crm_guess = next((c for c, aliases in CRM_ALIASES.items() if any(a in low for a in aliases)), "")
    return tools, crm_guess


# --- Merge logic ---------------------------------------------------------------
def norm(s):
    return re.sub(r"\s+", " ", str(s)).strip().lower()


def find_member(members, speaker):
    """Match a transcript speaker to a member. Returns index or None.
    Exact (normalized) match first; then unambiguous first-name match."""
    sp = norm(speaker)
    for i, m in enumerate(members):
        if norm(m.get("name", "")) == sp:
            return i
    # first-name / prefix match, only if exactly one candidate (avoid Daniel collisions)
    cands = []
    for i, m in enumerate(members):
        name = norm(m.get("name", ""))
        if name and (name.startswith(sp + " ") or sp.startswith(name + " ") or
                     name.split(" ")[0] == sp or sp.split(" ")[0] == name):
            cands.append(i)
    return cands[0] if len(cands) == 1 else None


def merge_list(existing, new):
    """Add items from new that aren't already in existing (case-insensitive)."""
    seen = {norm(x) for x in existing}
    added = []
    for item in new:
        if norm(item) not in seen:
            existing.append(item)
            seen.add(norm(item))
            added.append(item)
    return added


def new_member_record(speaker, tools, crm_guess, source):
    return {
        "name": speaker,
        "role": "(auto-added - needs review)",
        "city": "",
        "website": "",
        "socials": {},
        "crm": crm_guess,
        "usesVAs": False,
        "aiPowerhouse": False,
        "openToOneToOne": False,
        "marketSplit": {},
        "turnoverBand": "Undisclosed",
        "tools": tools,
        "needsReview": True,
    }


def update_roster(members, speaker_signals, source):
    """Mutates members in place. Returns a structured change summary."""
    summary = {"updated": [], "added": [], "ambiguous": []}
    for speaker, (tools, crm_guess) in speaker_signals.items():
        if not tools and not crm_guess:
            continue  # nothing worth recording for this speaker
        idx = find_member(members, speaker)
        if idx is None:
            members.append(new_member_record(speaker, tools, crm_guess, source))
            summary["added"].append({"name": speaker, "tools": tools})
            continue
        m = members[idx]
        m.setdefault("tools", [])
        added_tools = merge_list(m["tools"], tools)
        crm_set = ""
        if crm_guess and not m.get("crm"):
            m["crm"] = crm_guess
            crm_set = crm_guess
        if added_tools or crm_set:
            summary["updated"].append({"name": m["name"], "tools": added_tools, "crm": crm_set})
    return summary


# --- Reporting -----------------------------------------------------------------
def print_summary(summary, dry_run):
    print("\n=== Roster update summary%s ===" % (" (DRY RUN - nothing written)" if dry_run else ""))
    if not summary["updated"] and not summary["added"]:
        print("No changes: no new tools or CRM detected for known or new speakers.")
        return
    for u in summary["updated"]:
        bits = []
        if u["tools"]:
            bits.append("tools +[%s]" % ", ".join(u["tools"]))
        if u["crm"]:
            bits.append("crm=%s" % u["crm"])
        print("  ~ %-16s %s" % (u["name"], "; ".join(bits)))
    for a in summary["added"]:
        print("  + %-16s NEW (needs review) tools=[%s]" % (a["name"], ", ".join(a["tools"])))
    if summary["ambiguous"]:
        print("  ? ambiguous speakers skipped: %s" % ", ".join(summary["ambiguous"]))
    print("Totals: %d updated, %d added.\n" % (len(summary["updated"]), len(summary["added"])))


# --- Main ----------------------------------------------------------------------
def main(argv=None):
    parser = argparse.ArgumentParser(description="Merge a Zoom transcript into members.json")
    parser.add_argument("transcript", help="path to transcript (.txt or .vtt)")
    parser.add_argument("--members", default="members.json", help="path to members.json (default: members.json)")
    parser.add_argument("--dry-run", action="store_true", help="show the summary but do not write changes")
    args = parser.parse_args(argv)

    if not os.path.exists(args.transcript):
        print("ERROR: transcript not found: %s" % args.transcript, file=sys.stderr)
        return 2
    if not os.path.exists(args.members):
        print("ERROR: members file not found: %s" % args.members, file=sys.stderr)
        return 2

    with open(args.transcript, "r", encoding="utf-8") as f:
        transcript_text = f.read()
    with open(args.members, "r", encoding="utf-8") as f:
        members = json.load(f)

    utterances = parse_transcript(transcript_text)
    by_speaker = aggregate_by_speaker(utterances)
    if not by_speaker:
        print("No speakers found. Is this a 'Name: text' transcript or a .vtt file?", file=sys.stderr)
        return 1

    signals = {sp: extract_speaker_signals(text) for sp, text in by_speaker.items()}
    source = os.path.basename(args.transcript)
    summary = update_roster(members, signals, source)
    print_summary(summary, args.dry_run)

    if args.dry_run:
        return 0
    if not summary["updated"] and not summary["added"]:
        return 0

    backup = args.members + ".bak"
    with open(backup, "w", encoding="utf-8") as f:
        with open(args.members, "r", encoding="utf-8") as orig:
            f.write(orig.read())
    with open(args.members, "w", encoding="utf-8") as f:
        json.dump(members, f, indent=2, ensure_ascii=False)
        f.write("\n")
    print("Wrote %s (backup at %s)." % (args.members, backup))
    return 0


if __name__ == "__main__":
    sys.exit(main())
