---
project: Logbook
status: testing
owner: PathToFluent
type: Python script with a browser page
created: 2026-11-26
updated: 2026-11-26
---

# PathToFluent Logbook

## 1. Goal
I want one place that records the time I spend with Spanish (shows, Pimsleur lessons, podcasts, reading, conversation) next to my card numbers from Waypoint. "Working" means logging a session takes a few seconds, I can see my hours and known words add up, and the data sits in a plain file that my tutor agent can read to draft a progress post for me to approve.

## 2. How I'll use it
1. I finish a Pimsleur lesson or an episode. I open Logbook in my browser.
2. I tap a recent item (the next lesson or episode is already suggested with its usual duration), or I type a new one: what it was, the type, how long.
3. The entry appears in the list and my totals update.
4. Card numbers appear by themselves. Waypoint writes them each time it reconciles; I never type them.
5. Once a week my tutor agent reads the log and sends me a draft post. I approve it, edit it, or skip it. Nothing is posted without my yes.
6. When I cross a milestone (100 hours, 500 known words), the draft that week says so.

## 3. Rules

**Entries**
1. An entry has: date, type, title, duration in minutes, and an optional note and link.
2. Types are: show, course, podcast, reading, conversation, other. Pimsleur is a course.
3. The date defaults to today. I can set any past date. A future date is refused.
4. Duration is required and must be between 1 and 1,440 minutes.
5. Each language has its own log file and its own totals, streak and milestones. The page shows one language at a time, with a switch at the top. Spanish is the first.
6. I can edit or delete any entry. Deleting asks me to confirm first.
7. Two entries with the same date, title and duration are allowed (I may watch something twice), but Logbook asks "log it again?" before saving the second.

**Fast entry**
7a. A Clear button empties What, Minutes, Note and Link without saving anything.
7b. A Look up button asks for the duration directly, and always says what happened or why not.
8. Logbook remembers each title with its type and last duration, and offers matches as I type.
9. If a title ends in a number ("Lesson 5", "S01E03"), Logbook offers the next one in the series ("Lesson 6", "S01E04") with the same type and duration.
10. The five most recent series show as one-tap buttons at the top of the page.

**Durations from a link or a title**
10a. If I paste a YouTube link, Logbook fills in the title and duration from the public page. No login is used.
10b. If I type a show and episode ("El crimen de Pazos S01E02"), Logbook looks up the episode's running time in TMDB, using the same free key as Scout. This is optional and off until I add a key.
10c. If a lookup fails or there is no internet, the form stays as I left it and I type the duration myself. A lookup never blocks saving.
10d. Logbook never signs in to anything and never reads my browser's logins. A Netflix link is kept on the entry as a link only.

**Card numbers**
11. Logbook reads card numbers from a stats file that Waypoint writes. It never opens Anki and never reads my collection.
12. The stats file holds one line per day and language: date, known words, words being learned, known sentences, cards studied so far, cards ready, cards waiting. A second reconcile on the same day replaces that day's line.
12a. If the stats file is damaged, Logbook says so in the Cards section and carries on with time only. The log is not affected.
12b. A line dated after today is ignored. If Waypoint hasn't run lately, the newest line is shown with its date.
13. If the stats file is missing, Logbook works as normal and shows time only.
14. Logbook never writes to the stats file, and Waypoint never writes to the log. Either tool works without the other.
14a. Time spent on Anki reviews is not counted as hours. Card numbers are shown beside the hours, not added to them.

**Totals**
15. The page shows hours for this week, this month and all time, in total and by type.
16. A week runs Monday to Sunday.
17. The page shows known words today and the change over the last 7 and 30 days, when the stats file has those days.
18. A streak is the number of days in a row, ending today or yesterday, with at least one entry.

**Milestones**
19. Milestones are: total hours at 10, 25, 50, 100, then every 100; known words at 100, 250, 500, 1,000, then every 500; each show or course finished (I mark it finished myself).
20. A milestone is recorded once, dated the day it was first passed. Deleting entries later does not remove it.
20a. A "finished" mark I made by mistake can be removed, after a confirm. Hours and known-words milestones can't be removed.
20b. The page shows how far I am from the next hours and known-words milestones.

**The hand-off**
21. After every change, and whenever the page loads, Logbook brings that language's summary file up to date: this week's and last week's totals and entries, this month's and all-time totals, the streak, card numbers, how far to the next milestones, every milestone, and the milestones that are new since the summary was last used for a post.
21a. "Last used" is a small marker file. Running `python3 logbook.py --mark-used --folder <folder>` sets it to now. Until it exists, every milestone counts as new.
21b. `python3 logbook.py --summary --folder <folder>` brings the summary up to date without opening the page, so a scheduled job can refresh it first.
22. Logbook does not write posts and does not talk to X. Drafting belongs to the agent; posting needs my approval each time.
23. The summary holds only what I typed and the numbers. No file paths, no account names, no links.

**Safety of the data**
24. The log is one plain file I can open, read and back up myself.
25. Before each save, Logbook keeps the previous version as a backup copy. It keeps the last 10.
26. If the log file can't be read, Logbook stops and says so. It never starts a fresh log over a broken one.

## 4. Examples

| # | Given | Expected |
|---|-------|----------|
| 1 | I type "Pimsleur Spanish L1 Lesson 5", type course, 30 min | Entry saved for today. Week and all-time totals rise by 30 minutes. |
| 2 | The next day I open Logbook | A one-tap button offers "Pimsleur Spanish L1 Lesson 6", course, 30 min. |
| 3 | I log "El crimen de Pazos S01E01", show, 52 min | Saved. Next time the button offers "El crimen de Pazos S01E02", show, 52 min. |
| 4 | I enter a duration of 0, or leave it blank | Refused with a plain message. Nothing saved. |
| 5 | I log the same title, date and duration twice | Logbook asks "log it again?". Yes saves a second entry; no saves nothing. |
| 6 | The Waypoint stats file does not exist | The page shows time totals, and "No card numbers yet" where the word counts would be. |
| 7 | Waypoint reconciles three times in one day | The stats file has one line for that day, holding the last numbers. |
| 8 | My all-time total goes from 99 h 40 min to 100 h 10 min | A "100 hours" milestone is recorded with today's date and appears in the summary. |
| 9 | I then delete a 60-minute entry, taking me back under 100 hours | The total drops. The milestone stays recorded and is not announced a second time when I pass 100 again. |
| 10 | I log on Mon, Tue, Wed, skip Thu, log Fri | On Friday the streak is 1. |
| 11 | I set the date to tomorrow | Refused. |
| 12 | The log file is damaged | Logbook shows an error naming the file and the newest backup. It saves nothing until I fix or restore it. |
| 13 | I paste a YouTube link while online | Title and duration fill in. I can change either before saving. |
| 14 | I paste a YouTube link with no internet | Nothing fills in, a short note says the lookup failed, and I can still type and save. |
| 15 | I switch the page to French and log a lesson | It goes into the French log. Spanish totals, streak and milestones do not change. |

## 5. Not doing
- No posting to X or anywhere else. No accounts, no passwords, no keys.
- No reading of Anki's collection or database.
- No timers or automatic tracking of what I watch. I log it myself.
- No signing in to Netflix or any other service, and no reading of my browser's logins.
- No Netflix history import in the first version.
- No logging from my phone for now. Everything is done on my Mac.
- No counting of Anki review time.
- No charts in the first version. Numbers first.

## 6. Inputs and outputs
- **Reads:** `logbook-es.json` (my entries, one file per language); `waypoint_stats.json` (written by Waypoint, optional).
- **Writes:** `logbook-es.json`; `logbook_summary-es.json` (for the agent); `logbook_summary_used-es.json` (the "last used" marker, only when asked); `backups/logbook-es-<date-time>.json`.
- **Folder:** one data folder that I choose the first time I run it and can change in settings. Nothing is hard-coded. I'll start with my existing hand-off folder.
- **Settings I can change:** data folder; where the Waypoint stats file is; languages; the type list; TMDB key (optional); link lookups on or off; the milestone steps; the day the week starts.
- **Needed from Waypoint:** a small change so each reconcile writes that day's line to `waypoint_stats.json` in a folder I choose (off by default).

## 7. Where it runs
- My Mac, and anything else with Python 3.9 or newer. Standard library only, nothing to install.
- One file, `logbook.py`. Running it opens the page in my browser, the same way Trailblazer does.
- Works with no internet. Only the optional link and title lookups need it.

## 8. Decisions made

| Decision | Why |
|----------|-----|
| Its own tool, not part of Waypoint | It tracks time, not cards. Each tool stays small and works alone. |
| Named Logbook | Logging is what it does daily; milestones come out of it. |
| Card numbers arrive through a file Waypoint writes | Keeps Logbook out of Anki and keeps both tools standalone. |
| Plain JSON file, not a database | I can read it, back it up, and an agent can read it with no extra tools. |
| The agent drafts, I approve, then it posts | It's my public voice. |
| Weekly post plus milestone posts | Daily numbers are dull; weekly ones mean something. |
| Milestones are never un-recorded | Avoids announcing the same one twice. |
| Browser page, like Trailblazer | Same look and habits; nothing new to learn. |
| Settings (the folder choice) live in `~/.pathtofluent/logbook-settings.json` | Keeps my personal path out of the tool's own folder and out of the repo. |
| A missing duration is refused by Logbook itself, not by the browser | One plain message for every bad duration. |
| "Same title" for the log-it-again question ignores capital letters | "lesson 5" and "Lesson 5" are the same session. |
| Tapping a "Next up" button fills the form; I still press Add | Episode lengths vary, so I get to see the duration before it is saved. |
| An entry with a link never produces a "next one" | A YouTube video called "Easy Spanish 301" has no predictable 302. |
| The TMDB key is kept in the settings file in my home folder and never sent to the page | It stays out of the data folder, the log and the repo. |
| Lookups only ever fetch addresses Logbook builds itself, on youtube.com and themoviedb.org | A pasted link can't make Logbook fetch anything else. |
| "Cards studied" is the running total of cards studied at least once, not a per-day count | Waypoint already has it for free, and the difference between two days gives the daily figure. |
| The stats file is looked for in the data folder unless I point Settings somewhere else | One folder to think about by default. |
| The summary carries last week as well as this week | A draft written on Monday morning still has a full week to talk about. |
| On first use, every milestone already passed is recorded and counts as new | The agent drafting a post should mention only the highest of each kind. |
| The draft reaches me as a phone notification in the scheduled task's own chat, and I approve by replying there | No extra app or inbox to check. |
| After I approve, the agent posts through Chrome on my Mac and then writes the "last used" marker itself | The scheduled job can't run `logbook.py`, which lives outside the folder it is allowed to see. |
| Time stamps on milestones and the marker are UTC | The job's clock and my Mac's clock are in different zones. |
| The weekly job runs Sundays at 5:47pm my local time | A few minutes off the hour avoids busy scheduling slots; my assistant moves the zone when I travel. |
| One log per language | Keeps each language's numbers clean and separate. |
| Anki review time is not counted | The card numbers already show that work. |
| Mac only for now | Simpler; phone logging can come later. |
| Durations come from public pages and TMDB, never from my logins | A local script can't safely use my browser's sign-ins, and shouldn't. |
| Weekly draft reaches me Sunday 6pm local time; the approved post goes out Monday 9am US Eastern | The week closes Sunday; Monday morning is a reasonable first slot. Revisit after two months of X analytics. |

## 9. Open questions
- [ ] Me: keep an eye on how often TMDB has the running time for the shows I watch.
- [ ] Claude: check what Netflix's viewing-history download contains today (for a later stage).

## 10. Build stages
- [x] **Stage 1:** `logbook.py` with the quick-add form, the entry list, edit and delete, totals, backups. Time only.
- [x] **Stage 2:** Fast entry: remembered titles, next-in-series suggestions, one-tap buttons, YouTube link and TMDB lookups.
- [x] **Stage 3:** Waypoint writes `waypoint_stats.json`; Logbook shows card numbers and their change.
- [x] **Stage 4:** Milestones and `logbook_summary.json`.
- [x] **Stage 5:** The tutor agent's weekly routine: read the summary, draft a post, send it to me for approval.
- [ ] **Later:** a second language; charts; Netflix history import; logging from my phone; Trailblazer adds an entry suggestion for each episode it builds.

## 11. How to check it works
- Stage 1: run `python3 logbook.py`, add the entries from examples 1, 3 and 4, and compare the totals by hand. Open `logbook-es.json` and confirm the entries are readable. Add one more entry and confirm a file appears in `backups/`.
- Stage 2: examples 2, 3, 5, 13 and 14.
- Stage 3: reconcile in Anki, then reload Logbook and compare the known-word count with Waypoint's "Show numbers".
- Stage 4: examples 8 and 9, using a test log with made-up hours.
- The rules about totals, streaks, series and milestones will have automated tests. The browser page and the Anki side can only be checked on my Mac.

## 12. Instructions for Claude
- Read this whole file before writing anything.
- Build only the next unchecked stage, then stop and tell me what to test.
- If a rule is unclear or two rules conflict, ask me before building. For small details not covered here, decide, and record the choice under "Decisions made".
- Check the examples in section 4 against the code and tell me which pass.
- Tell me plainly what you could not test.
- Original code only. AGPL-3.0, like the other tools.
- Nothing private in the repo: no names, no personal paths, no chat links, no keys.
- When done, update: status, the stage checkboxes, "Decisions made", and the log.

## 13. Log
- 2026-11-26: Stage 5 set up: a scheduled task drafts the weekly post on Sundays, sends two versions for approval, posts the approved one and writes the marker. Logbook 0.4.1 (UTC stamps). The first real run is the test; nothing about the routine has run yet.
- 2026-11-26: Stage 4 built, version 0.4.0: milestones (hours, known words, finished shows and courses), the Milestones section, `logbook_summary-es.json`, the last-used marker, and the `--summary` / `--mark-used` commands. 39 tests pass (adds examples 8 and 9). Page checked in a headless browser. Not yet run on my Mac. Next: stage 5, the weekly draft routine.
- 2026-11-26: Stage 3 built. Logbook 0.3.0 shows a Cards section from `waypoint_stats.json`; Waypoint 0.7.0 writes that file when a "Daily numbers folder" is chosen. 30 Logbook tests and 6 new Waypoint tests pass, including one that reads a file written by Waypoint's own code (examples 6 and 7). Page checked in a headless browser. Waypoint's new setting and the write at reconcile are untested inside Anki. Real lookups confirmed working by me on my Mac.
- 2026-11-26: 0.2.1 after first Mac test. YouTube lookup had failed with "no connection" and the episode lookup showed nothing. Added: certificate fallback and real failure reasons, a Look up button, a Clear button, 1x02 titles. 24 tests pass. Real lookups still unconfirmed.
- 2026-11-26: Stage 2 built, version 0.2.0: Next up buttons, remembered titles, YouTube link and TMDB episode lookups, Settings dialog. 22 automated tests pass (adds examples 2, 3, 13, 14). Page checked in a headless browser with stand-in answers for YouTube and TMDB. The real YouTube and TMDB lookups have NOT been tried: my build machine can't reach either site. Next: my test of both lookups, then stage 3.
- 2026-11-26: Stage 1 built as `logbook.py` 0.1.0. 14 automated tests pass (examples 1, 4, 5, 10, 11, 12, 15 and the totals, backup, edit and delete rules). Page checked in a headless browser: add, duplicate question, edit, delete, folder picker. Not yet run on a Mac. Next: my test, then stage 2.
- 2026-11-26: Open questions answered: hand-off folder (selectable), Mac only, no Anki time, one log per language, weekly draft Sunday evening, durations from YouTube links and TMDB.
- 2026-11-26: Idea shaped in chat and spec written. Nothing built. Next: my review, answers to the open questions, then stage 1.
