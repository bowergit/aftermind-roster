# The Aftermind Roster

A searchable directory of **The Aftermind** mastermind group — who uses which tools
and who can speak to which topics, so any member knows who to go to with a question.

Live site: **https://bowergit.github.io/aftermind-roster/**

---

## What's in here

| File | Purpose |
|------|---------|
| `index.html` | The whole app — plain HTML/CSS/vanilla JS, no build step, no framework. Fetches `members.json` at load. |
| `members.json` | The member data. **This is the only file automation needs to touch.** |
| `update-roster.py` | Script that reads a Zoom transcript and merges newly-mentioned tools/topics into `members.json`. |
| `sample-transcript.txt` | A fake transcript for testing the script. |
| `.nojekyll` | Tells GitHub Pages to serve files as-is. |
| `.claude/launch.json` | Local dev-server config for previewing (optional). |

## How the data works

Every member is one object in `members.json`:

```json
{
  "name": "Daniel Bower",
  "role": "Magician and host, London",
  "blurb": "One-line description.",
  "website": "https://...",
  "crm": "Zoho CRM",              // a single CRM
  "usesVAs": false,               // tickbox: do they use virtual assistants
  "markets": ["Corporate"],       // any of: Corporate, Weddings, Private parties, Other
  "turnoverBand": "Undisclosed",  // USD band in $50k intervals, or "Undisclosed"
  "openToOneToOne": true,         // happy to take a 1:1 if a member has questions
  "tools": ["Claude", "17hats"],
  "topics": ["Marketing systems", "Lead scoring"],
  "needsReview": false            // true = auto-added by the script, not yet verified
}
```

The page reads this file with `fetch()` — so **automation can edit `members.json`
directly without touching `index.html`.**

## Editing from the page (proof of concept)

The site has no login and no backend. Anyone can:

- **Search** by name, tool, topic, CRM, or market.
- **Filter** with the tool / topic / market chips (selecting more than one narrows
  the list — a member must match *all* selected chips).
- **Edit** any member, or **Add yourself** via the questionnaire.
- Follow each member's **website** link and see whether they're open to a **1:1**.

> ⚠️ Edits and new entries are saved in **your browser's localStorage only** — they
> do **not** sync to other people yet. To publish a change to the whole group, click
> **Export members.json** (or **Copy JSON**), then commit the updated file to this repo.
> **Reset to published** discards your local edits and reloads the committed data.

Real multi-user editing would need a backend or a GitHub-API-backed form — that's a
deliberate later step, not wired up yet.

---

## Running the update script

The script merges tools/topics found in a Zoom transcript into `members.json`.
It needs only Python 3 (3.8+) — no third-party packages, no API key, no network.

It accepts a plain-text transcript (`Name: text` lines) **or** a Zoom `.vtt` file.

### Preview the changes without writing (recommended first)

```bash
python update-roster.py sample-transcript.txt --dry-run
```

### Apply the changes to members.json

```bash
python update-roster.py path/to/your-transcript.vtt
```

That writes the updated `members.json` and saves a backup to `members.json.bak`.

### Options

```
python update-roster.py <transcript.(txt|vtt)> [--members members.json] [--dry-run]

  transcript        Path to the Zoom transcript (.txt or .vtt).
  --members PATH    Which roster file to update (default: members.json).
  --dry-run         Print the change summary but write nothing.
```

### What it does

- Splits the transcript into per-speaker utterances.
- Detects which **tools** each speaker mentioned (any mention counts) and which
  **topics** they spoke about with some depth (a topic needs at least two trigger
  hits, so a passing mention won't qualify).
- For a speaker **already in** `members.json`: merges new tools/topics into their
  tags with no duplicates, and sets their `crm` only if it's currently empty.
- For a speaker **not yet in** `members.json`: adds a new entry inferred from
  context, flagged `"needsReview": true` (shown with a *needs review* badge on the
  site) so you can check it before trusting it.
- Prints a short diff of exactly what changed.

The tool/topic detection is intentionally simple (keyword/dictionary based) so the
script runs standing alone. It lives in one function, `extract_speaker_signals()`,
so it can be swapped for an LLM-backed extractor later without changing the rest of
the pipeline. Edit `TOOL_ALIASES` and `TOPIC_TRIGGERS` near the top of the script to
teach it new tools or topics.

### Not wired up yet (on purpose)

No scheduling and no auto-commit. Run it by hand for now; whether it later runs via a
GitHub Action, a Claude Code Remote trigger, or manually after each call is a separate
decision.

---

## Local preview

Because the page uses `fetch()`, open it through a local web server, not as a
`file://` URL:

```bash
cd aftermind-roster
python -m http.server 8731
# then visit http://localhost:8731
```

## Deploying (GitHub Pages)

This repo is meant to deploy from the `main` branch, root folder. In the repo on
GitHub: **Settings → Pages → Build and deployment → Deploy from a branch → `main` /
`root`**. The site appears at `https://<your-username>.github.io/aftermind-roster/`.
