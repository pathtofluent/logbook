# PathToFluent Logbook

Keep a log of the time you spend with a language: shows, course lessons, podcasts, reading, conversation. See your hours add up by week, by month and in total.

Part of the [PathToFluent](https://github.com/pathtofluent) tools. It works on its own.

## What it does today (0.4.0)

- Log a session in a few seconds: what, type, minutes, date, and an optional note and link.
- **Next up** buttons: after "Lesson 5" or "S01E03", the next one is offered with its type and usual duration.
- Remembers your titles and offers them as you type.
- Paste a YouTube link and the title and duration fill in. No login is used.
- Type "Show name S01E02" and the episode length fills in from TMDB, if you add a free TMDB key in Settings.
- **Card numbers** from PathToFluent Waypoint, if you use it: known words and how they changed over 7 and 30 days, words being learned, cards studied, cards waiting. Logbook only reads Waypoint's `waypoint_stats.json`; it never opens Anki.
- **Milestones**: hours (10, 25, 50, 100, then every 100), known words (100, 250, 500, 1,000, then every 500), and shows or courses you mark as finished. Each is recorded once and dated the day you passed it.
- Totals for this week, this month and all time, in total and by type, plus your streak.
- Edit or delete any entry.
- One plain file per language (`logbook-es.json`) in a folder you choose. You can read it and back it up yourself.
- A backup of the previous version before every save. The last 10 are kept.
- If the log file is damaged, Logbook stops and tells you. It never writes over it.

See `SPEC.md` for the rules and what's planned.

## Run it

You need Python 3.9 or newer. There is nothing to install.

```
python3 logbook.py
```

The page opens in your browser. The first time, choose the folder where your log should live. Leave the terminal window open while you use it, and press Quit on the page when you're done.

## The summary file

Logbook keeps `logbook_summary-es.json` up to date beside your log: this week and last week, month and all-time totals, your streak, card numbers, milestones, and how far the next ones are. It holds only what you typed and the numbers, so a script or an assistant can turn it into a progress post without touching your log.

```
python3 logbook.py --summary --folder /path/to/your/folder     # refresh it without opening the page
python3 logbook.py --mark-used --folder /path/to/your/folder   # note that it was used; milestones stop counting as new
```

The marker is `logbook_summary_used-es.json`, holding `{"used": "2026-11-29T23:50:00"}` in UTC. A script may write that file itself.

## Privacy

Your log stays on your computer. Logbook has no accounts and only answers requests from your own machine.

The only time it goes online is a lookup you trigger: it fetches the public YouTube page for a link you paste, or asks TMDB about a show title you type. It never signs in to anything and never reads your browser's logins. You can turn lookups off in Settings.

Your folder choice and TMDB key (if you add one) are kept in `~/.pathtofluent/logbook-settings.json`.

## Tests

```
python3 tests/test_logbook.py
```

## Licence

AGPL-3.0. See `LICENSE`.
