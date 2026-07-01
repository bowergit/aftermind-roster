# The Aftermind Roster

A searchable directory of **The Aftermind** mastermind group — who uses which tools
and CRMs and which markets they work, so any member knows who to go to with a question.

Live site: **https://bowergit.github.io/aftermind-roster/**

---

## What's in here

| File | Purpose |
|------|---------|
| `index.html` | The whole app — plain HTML/CSS/vanilla JS, no build step, no framework. Reads/writes a **Supabase** database via its REST API (plain `fetch`, no SDK). |
| `members.json` | Seed data / export format. The live site no longer reads this at runtime, but `update-roster.py` operates on it and it's the schema reference + a backup. |
| `update-roster.py` | Script that reads a Zoom transcript and merges newly-mentioned tools (and CRM) into `members.json`. |
| `sample-transcript.txt` | A fake transcript for testing the script. |
| `.nojekyll` | Tells GitHub Pages to serve files as-is. |
| `.claude/launch.json` | Local dev-server config for previewing (optional). |

## How the data works

The roster data lives in a **Supabase** Postgres table called `members`. Each row is
`{ id, data, updated_at }` where `data` is one member object:

```json
{
  "name": "Daniel Bower",
  "role": "Magician & host",
  "city": "London",
  "website": "https://...",
  "websitePlatform": "Squarespace", // Squarespace/Wix/WordPress/Webflow/Showit/Lovable/GHL or free text
  "socials": {                    // any of: instagram, facebook, youtube, tiktok, x, linkedin
    "instagram": "https://instagram.com/..."
  },
  "crm": "",                      // one of: 17Hats, Mago, HoneyBook, SpeakerFlow, GHL, or free text
  "usesVAs": false,               // tickbox: do they use virtual assistants
  "aiPowerhouse": false,          // tickbox: heavy AI user
  "openToOneToOne": false,        // happy to take a 1:1 if a member has questions
  "marketSplit": {                // % of gigs/turnover by market, totals 100 (or {} = unspecified)
    "Corporate": 60, "Weddings": 40
  },
  "turnoverBand": "Undisclosed",  // USD band in $50k intervals, or "Undisclosed"
  "tools": ["Claude", "17hats"],
  "needsReview": true             // legacy flag kept on stored rows; the UI no longer uses it
}
```

Cards show an **"incomplete"** badge until a profile has most of its details filled in
(city, website, Instagram, CRM, market split, tools — turnover is optional). Clicking
the badge opens that member's edit form, and the **Incomplete only** button filters to
profiles still missing details.

Markets are one of: **Corporate, Weddings, Private parties, Other**. There are no
`blurb` or `topics` fields — everyone in the group can speak to anything, and the
per-member self-data (CRM, turnover, VAs, AI, 1:1, market split, tools) starts blank
for each person to fill in.

`index.html` loads all rows on page load and writes edits straight back to the
database, so **changes are shared — everyone sees them immediately.**

## Editing from the page

No login (proof of concept). Anyone with the page can:

- **Search** by name, city, tool, CRM, market, or website platform.
- **Filter** with the tool / market / "built on" chips (selecting more than one
  narrows the list — a member must match *all* selected chips). Chips appear as
  members fill in their tools, market split, and platform — so you can, e.g., click
  **Squarespace** to see everyone on Squarespace, or **Claude** to see every Claude user.
- **Tools** use a shared autocomplete: start typing in the edit form and pick an
  existing tool, or add a new one — new tools join the shared list everyone filters by.
- **⚠ Needs review** button: show only profiles that were auto-researched and still
  need a human to confirm them.
- **Edit** any member, or **Add yourself** via the questionnaire. Saves persist to the
  shared database.
- **Refresh** re-pulls the latest data (e.g. after someone else edits).
- **Export / Copy JSON** downloads the current roster as `members.json` (for the script
  or a backup).

> Deleting a profile is **not** possible from the page (no delete policy), to avoid
> accidental/​malicious wipes. Remove a row from the Supabase dashboard if needed.

### Supabase setup (already done for this project)

The table was created with this SQL (RLS on; public read + insert + update, no delete):

```sql
create table public.members (
  id bigint generated always as identity primary key,
  data jsonb not null,
  updated_at timestamptz default now()
);
alter table public.members enable row level security;
create policy "public read"   on public.members for select using (true);
create policy "public insert" on public.members for insert with check (true);
create policy "public update" on public.members for update using (true) with check (true);
```

The project URL and **publishable** (anon) key live at the top of `index.html` under
`SUPABASE_URL` / `SUPABASE_KEY`. The publishable key is designed to be shipped in the
browser — the **secret** `service_role` key must never go in this file. To re-seed the
table from `members.json`, POST each member wrapped as `{ "data": <member> }` to
`<URL>/rest/v1/members`.

> **Security note:** because there's no login, anyone with the page can edit any
> profile. That's the accepted proof-of-concept tradeoff. To tighten later: add a shared
> edit passphrase, scope the update policy, or require auth.

---

## Running the update script

The script merges tools (and CRM) found in a Zoom transcript into `members.json`.
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
- Detects which **tools** each speaker mentioned (any mention counts) and, if they
  named one of the known **CRMs**, which one.
- For a speaker **already in** `members.json`: merges new tools into their list with
  no duplicates, and sets their `crm` only if it's currently empty.
- For a speaker **not yet in** `members.json`: adds a new entry (name + tools + CRM).
  New entries start with blank self-data, so they show as *incomplete* on the site
  until reviewed/filled in.
- Prints a short diff of exactly what changed.

The detection is intentionally simple (keyword/dictionary based) so the script runs
standing alone. It lives in one function, `extract_speaker_signals()`, so it can be
swapped for an LLM-backed extractor later without changing the rest of the pipeline.
Edit `TOOL_ALIASES` and `CRM_ALIASES` near the top of the script to teach it new tools
or CRMs.

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
