# Changelog

## 0.4.1 - 2026-11-26
- Milestone and "last used" time stamps are now in UTC, so a summary marked as used from another machine compares correctly.

## 0.4.0 - 2026-11-26
- Milestones for hours, known words, and shows or courses you mark as finished, with a Milestones section showing how far the next ones are.
- A summary file (`logbook_summary-<language>.json`) kept up to date for scripts and assistants.
- `--summary` and `--mark-used` commands to refresh the summary and note that it was used.

## 0.3.0 - 2026-11-26
- Cards section: known words with their 7- and 30-day change, words being learned, cards studied and cards waiting, read from PathToFluent Waypoint's `waypoint_stats.json`.
- Settings: choose another folder for that file if it isn't in the data folder.
- Without the file, or with a damaged one, Logbook shows time only.

## 0.2.1 - 2026-11-26
- Clear button empties the form.
- Look up button next to Minutes, so a lookup can be asked for directly and always says what happened.
- Secure lookups now try the system's certificates when Python has none of its own (common on macOS), and a failed lookup says why.
- Episode titles can also be written 1x02. Pressing Enter waits for a lookup that is still running.

## 0.2.0 - 2026-11-26
- Next up buttons for the next lesson or episode in a series.
- Remembered titles offered as you type.
- Durations filled in from a YouTube link, or from TMDB for "Show S01E02" titles (optional key).
- Settings dialog: data folder, lookups on or off, TMDB key.

## 0.1.0 - 2026-11-26
- First version: log sessions, see totals by week, month and all time, edit and delete entries.
- One log file per language, a backup before every save, and a damaged log is never overwritten.
