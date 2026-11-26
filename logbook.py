#!/usr/bin/env python3
"""
PathToFluent Logbook - keep a log of the time you spend with a language.

Log shows, course lessons, podcasts, reading and conversation, and see your
hours add up by week, by month and in total. Everything is saved as a plain
file in a folder you choose.

Requirements: Python 3.9+. Nothing to install.
Run:          python3 logbook.py
The interface opens in your browser. Nothing leaves your computer.
"""
import argparse, datetime, html, json, os, re, secrets, shutil, string, sys, threading, uuid, webbrowser
import ssl, urllib.error, urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs, urlencode, quote

APP, VERSION = "PathToFluent Logbook", "0.4.1"
TOKEN = secrets.token_urlsafe(16)
TYPES = ["show", "course", "podcast", "reading", "conversation", "other"]
MAX_MINUTES = 1440
KEEP_BACKUPS = 10
DEFAULT_SETTINGS = {"folder": "", "languages": [{"code": "es", "name": "Spanish"}], "week_start": 0,
                    "lookups": True, "tmdb_key": "", "stats_folder": ""}
STATS_FILE = "waypoint_stats.json"      # written by PathToFluent Waypoint; Logbook only reads it
BUTTONS = 5                       # one-tap "next up" buttons
REMEMBERED = 300                  # titles offered while typing
LOCK = threading.Lock()


class LogError(Exception):
    """The log file exists but can't be used. Nothing may be saved over it."""


# ───────────────────────────── settings ─────────────────────────────
def settings_path():
    return os.environ.get("LOGBOOK_SETTINGS") or os.path.join(
        os.path.expanduser("~"), ".pathtofluent", "logbook-settings.json")


def load_settings():
    s = dict(DEFAULT_SETTINGS)
    try:
        with open(settings_path(), encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            s.update({k: data[k] for k in DEFAULT_SETTINGS if k in data})
    except (OSError, ValueError):
        pass
    return s


def save_settings(s):
    p = settings_path()
    os.makedirs(os.path.dirname(p), exist_ok=True)
    write_json(p, s)


# ───────────────────────────── the log file ─────────────────────────────
def write_json(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
        f.write("\n")
    os.replace(tmp, path)


def log_path(folder, lang):
    return os.path.join(folder, "logbook-%s.json" % lang)


def backups(folder, lang):
    d = os.path.join(folder, "backups")
    pre = "logbook-%s-" % lang
    try:
        names = sorted(n for n in os.listdir(d) if n.startswith(pre) and n.endswith(".json"))
    except OSError:
        names = []
    return [os.path.join(d, n) for n in names]


def load_log(folder, lang):
    """The log as a dict. A missing file is an empty log; a damaged one raises LogError."""
    p = log_path(folder, lang)
    if not os.path.exists(p):
        return {"app": APP, "format": 1, "language": lang, "entries": [], "milestones": []}
    try:
        with open(p, encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict) or not isinstance(data.get("entries"), list):
            raise ValueError("not a Logbook file")
        for e in data["entries"]:
            if not isinstance(e, dict) or not isinstance(e.get("minutes"), int) or "date" not in e:
                raise ValueError("an entry is incomplete")
            datetime.date.fromisoformat(e["date"])
    except (OSError, ValueError) as err:
        old = backups(folder, lang)
        hint = ("The newest backup is %s." % os.path.basename(old[-1])) if old else "There is no backup yet."
        raise LogError("The log file %s can't be read (%s). Nothing will be saved until it is fixed or "
                       "restored. %s" % (os.path.basename(p), err, hint))
    data.setdefault("milestones", [])
    return data


def save_log(folder, lang, data, now=None):
    """Keep the previous version as a backup (the last 10), then write the log."""
    p = log_path(folder, lang)
    if os.path.exists(p):
        d = os.path.join(folder, "backups")
        os.makedirs(d, exist_ok=True)
        stamp = (now or datetime.datetime.now()).strftime("%Y%m%d-%H%M%S-%f")
        shutil.copy2(p, os.path.join(d, "logbook-%s-%s.json" % (lang, stamp)))
        for old in backups(folder, lang)[:-KEEP_BACKUPS]:
            os.remove(old)
    write_json(p, data)


# ───────────────────────────── rules ─────────────────────────────
def clean_entry(raw, today):
    """A checked entry from what was typed, or ValueError with a plain message."""
    title = " ".join(str(raw.get("title") or "").split())
    if not title:
        raise ValueError("Give the entry a title.")
    if len(title) > 200:
        raise ValueError("That title is too long (200 characters at most).")
    kind = str(raw.get("type") or "")
    if kind not in TYPES:
        raise ValueError("Choose a type.")
    m = raw.get("minutes")
    if isinstance(m, str) and m.strip().isdigit():
        m = int(m.strip())
    if isinstance(m, bool) or not isinstance(m, int):
        raise ValueError("Enter the duration in minutes.")
    if not 1 <= m <= MAX_MINUTES:
        raise ValueError("The duration must be between 1 and %d minutes." % MAX_MINUTES)
    try:
        day = datetime.date.fromisoformat(str(raw.get("date") or today.isoformat()))
    except ValueError:
        raise ValueError("That date isn't valid.")
    if day > today:
        raise ValueError("The date can't be in the future.")
    note = str(raw.get("note") or "").strip()[:500]
    link = str(raw.get("link") or "").strip()[:500]
    if link and not re.match(r"https?://", link):
        raise ValueError("A link must start with http:// or https://")
    return {"date": day.isoformat(), "type": kind, "title": title, "minutes": m, "note": note, "link": link}


def is_duplicate(entries, e, skip_id=None):
    return any(x.get("id") != skip_id and x["date"] == e["date"] and x["minutes"] == e["minutes"]
               and x.get("title", "").lower() == e["title"].lower() for x in entries)


def ordered(entries):
    """Newest day first; within a day, the most recently added first."""
    rows = sorted(enumerate(entries), key=lambda p: (p[1]["date"], p[1].get("added", ""), p[0]), reverse=True)
    return [x for _, x in rows]


def streak(entries, today):
    """Days in a row with at least one entry, ending today or yesterday."""
    days = {x["date"] for x in entries}
    d = today if today.isoformat() in days else today - datetime.timedelta(days=1)
    n = 0
    while d.isoformat() in days:
        n += 1
        d -= datetime.timedelta(days=1)
    return n


def totals(entries, today, week_start=0):
    """Minutes for this week, this month and all time, each in total and by type."""
    week0 = today - datetime.timedelta(days=(today.weekday() - week_start) % 7)
    spans = {"week": lambda d: week0 <= d <= today,
             "month": lambda d: (d.year, d.month) == (today.year, today.month),
             "all": lambda d: True}
    out = {k: {"minutes": 0, "by_type": {}} for k in spans}
    for x in entries:
        d = datetime.date.fromisoformat(x["date"])
        for k, inside in spans.items():
            if inside(d):
                out[k]["minutes"] += x["minutes"]
                out[k]["by_type"][x["type"]] = out[k]["by_type"].get(x["type"], 0) + x["minutes"]
    out["streak"] = streak(entries, today)
    out["entries"] = len(entries)
    out["week_from"] = week0.isoformat()
    return out


# ───────────────────────────── card numbers ─────────────────────────────
def stats_path(settings):
    return os.path.join(settings.get("stats_folder") or settings.get("folder") or "", STATS_FILE)


def read_days(path, lang):
    """This language's lines from the Waypoint numbers file, oldest first. Missing file -> None."""
    if not os.path.isfile(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            days = json.load(f)["days"]
        out = []
        for d in days:
            if d.get("language", lang) == lang:
                datetime.date.fromisoformat(d["date"])
                out.append(d)
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        raise ValueError("The card numbers file can't be read. Logbook is showing time only.")
    return sorted(out, key=lambda d: d["date"])


def card_numbers(days, today):
    """The newest line, and how known words changed over the last 7 and 30 days where those days exist."""
    days = [d for d in days or [] if d["date"] <= today.isoformat()]
    if not days:
        return None
    num = lambda d, k: d[k] if isinstance(d.get(k), int) and not isinstance(d.get(k), bool) else None
    now = days[-1]

    def change(n):
        cut = (today - datetime.timedelta(days=n)).isoformat()
        then = [d for d in days if d["date"] <= cut]
        a, b = num(now, "known_words"), num(then[-1], "known_words") if then else None
        return a - b if a is not None and b is not None else None

    return {"date": now["date"], "known_words": num(now, "known_words"), "learning_words": num(now, "learning_words"),
            "cards_studied": num(now, "cards_studied"), "cards_waiting": num(now, "cards_waiting"),
            "change7": change(7), "change30": change(30)}


def cards_state(settings, lang, today):
    try:
        return {"numbers": card_numbers(read_days(stats_path(settings), lang), today), "note": ""}
    except ValueError as e:
        return {"numbers": None, "note": str(e)}


# ───────────────────────────── milestones ─────────────────────────────
def utc_stamp(now=None):
    """The moment something was recorded, in UTC, so stamps written on different machines compare correctly."""
    return (now or datetime.datetime.now(datetime.timezone.utc)).strftime("%Y-%m-%dT%H:%M:%S")


HOUR_STEPS, WORD_STEPS = ([10, 25, 50, 100], 100), ([100, 250, 500, 1000], 500)
LESSON_WORDS = {"lesson", "episode", "ep", "part", "chapter", "unit", "lección", "leccion", "capítulo", "capitulo",
                "episodio"}


def steps_upto(value, steps):
    """Every milestone step at or below `value`: the listed ones, then one every `then`."""
    firsts, then = steps
    out = [x for x in firsts if x <= value]
    x = firsts[-1] + then
    while x <= value:
        out.append(x)
        x += then
    return out


def next_step(value, steps):
    firsts, then = steps
    for x in firsts:
        if x > value:
            return x
    return (int(value - firsts[-1]) // then + 1) * then + firsts[-1]


def language_name(settings, lang):
    return next((l["name"] for l in settings["languages"] if l["code"] == lang), lang)


def new_milestones(log, days, lang_name, today, now=None):
    """Milestones passed but not yet recorded. Each is dated the day it was first passed."""
    have = {m.get("id") for m in log.get("milestones", [])}
    stamp = utc_stamp(now)
    out, total = [], 0
    crossed = {}
    for x in sorted(log["entries"], key=lambda x: x["date"]):
        before, total = total, total + x["minutes"]
        for h in steps_upto(total / 60, HOUR_STEPS):
            if h * 60 > before:
                crossed[h] = x["date"]
    for h in sorted(crossed):
        if "hours-%d" % h not in have:
            out.append({"id": "hours-%d" % h, "kind": "hours", "value": h, "date": min(crossed[h], today.isoformat()),
                        "label": "%s hours of %s" % (format(h, ","), lang_name), "recorded": stamp})
    reached = {}
    for d in days or []:
        k = d.get("known_words")
        if isinstance(k, int) and not isinstance(k, bool) and d["date"] <= today.isoformat():
            for w in steps_upto(k, WORD_STEPS):
                reached.setdefault(w, d["date"])
    for w in sorted(reached):
        if "words-%d" % w not in have:
            out.append({"id": "words-%d" % w, "kind": "words", "value": w, "date": reached[w],
                        "label": "%s known words" % format(w, ","), "recorded": stamp})
    return out


def finished_candidates(entries):
    """Names of shows and courses in the log, newest first, to offer when marking one finished."""
    out, seen = [], set()
    for x in ordered(entries):
        if x["type"] not in ("show", "course"):
            continue
        t = " ".join(x["title"].split())
        m = EPISODE.match(t)
        if m:
            name = m.group(1)
        else:
            n = NUM_TAIL.match(t)
            name = n.group(1) if n and n.group(1).strip() else t
            words = name.rstrip(" .:#-–").split()
            if len(words) > 1 and words[-1].lower() in LESSON_WORDS:
                words = words[:-1]
            name = " ".join(words)
        name = name.strip(" .:#-–")
        if name and name.lower() not in seen:
            seen.add(name.lower())
            out.append({"title": name, "type": x["type"]})
    return out[:50]


def progress(log, cards, today):
    """How far to the next hours and known-words milestones."""
    minutes = sum(x["minutes"] for x in log["entries"])
    nh = next_step(minutes / 60, HOUR_STEPS)
    out = {"hours_next": nh, "minutes_to_go": nh * 60 - minutes, "words_next": None, "words_to_go": None}
    k = (cards or {}).get("known_words")
    if isinstance(k, int):
        out["words_next"] = next_step(k, WORD_STEPS)
        out["words_to_go"] = out["words_next"] - k
    return out


# ───────────────────────────── the summary file ─────────────────────────────
def summary_path(folder, lang):
    return os.path.join(folder, "logbook_summary-%s.json" % lang)


def used_path(folder, lang):
    return os.path.join(folder, "logbook_summary_used-%s.json" % lang)


def last_used(folder, lang):
    """When the summary was last used for a post ('' if never). Written by mark_used, read here."""
    try:
        with open(used_path(folder, lang), encoding="utf-8") as f:
            v = json.load(f).get("used")
        datetime.datetime.fromisoformat(v)
        return v
    except (OSError, ValueError, TypeError, AttributeError):
        return ""


def mark_used(folder, lang, now=None):
    stamp = utc_stamp(now)
    write_json(used_path(folder, lang), {"used": stamp, "note": "UTC. Milestones recorded after this moment count as new."})
    return stamp


def span(entries, first, last):
    rows = [x for x in ordered(entries) if first.isoformat() <= x["date"] <= last.isoformat()]
    by = {}
    for x in rows:
        by[x["type"]] = by.get(x["type"], 0) + x["minutes"]
    minutes = sum(by.values())
    return {"from": first.isoformat(), "to": last.isoformat(), "minutes": minutes, "hours": round(minutes / 60, 1),
            "by_type": by, "entries": [{"date": x["date"], "type": x["type"], "title": x["title"],
                                        "minutes": x["minutes"], "note": x.get("note", "")} for x in reversed(rows)]}


def build_summary(log, lang, lang_name, cards, used, today, week_start=0):
    """What a post could be written from: only what was typed, and the numbers. No paths, no accounts."""
    week0 = today - datetime.timedelta(days=(today.weekday() - week_start) % 7)
    t = totals(log["entries"], today, week_start)
    dates = [x["date"] for x in log["entries"]]
    public = lambda m: {k: m.get(k) for k in ("date", "kind", "label", "value", "type") if m.get(k) is not None}
    ms = sorted(log.get("milestones", []), key=lambda m: (m.get("date", ""), m.get("recorded", "")))
    return {"app": APP, "format": 1, "language": lang, "language_name": lang_name, "date": today.isoformat(),
            "this_week": span(log["entries"], week0, week0 + datetime.timedelta(days=6)),
            "last_week": span(log["entries"], week0 - datetime.timedelta(days=7), week0 - datetime.timedelta(days=1)),
            "this_month": {"minutes": t["month"]["minutes"], "hours": round(t["month"]["minutes"] / 60, 1),
                           "by_type": t["month"]["by_type"]},
            "all_time": {"minutes": t["all"]["minutes"], "hours": round(t["all"]["minutes"] / 60, 1),
                         "by_type": t["all"]["by_type"], "entries": len(dates), "first_day": min(dates) if dates else None},
            "streak_days": t["streak"], "cards": cards, "next": progress(log, cards, today),
            "milestones_new": [public(m) for m in ms if m.get("recorded", "") > used],
            "milestones_all": [public(m) for m in ms], "summary_last_used": used or None}


def sync(settings, lang, today, log=None, save=False):
    """Record any new milestones and bring the summary file up to date. Returns (log, cards)."""
    folder = need_folder(settings)
    if log is None:
        log = load_log(folder, lang)
    try:
        days, note = read_days(stats_path(settings), lang), ""
    except ValueError as e:
        days, note = None, str(e)
    fresh = new_milestones(log, days, language_name(settings, lang), today)
    if fresh:
        log.setdefault("milestones", []).extend(fresh)
    if fresh or save:
        save_log(folder, lang, log)
    numbers = card_numbers(days, today)
    summary = build_summary(log, lang, language_name(settings, lang), numbers, last_used(folder, lang), today,
                            settings.get("week_start", 0))
    try:
        with open(summary_path(folder, lang), encoding="utf-8") as f:
            same = json.load(f) == summary
    except (OSError, ValueError):
        same = False
    if not same:
        write_json(summary_path(folder, lang), summary)
    return log, {"numbers": numbers, "note": note}


def finish(settings, lang, raw, today):
    """Mark a show or course finished. That is a milestone I record myself."""
    title = " ".join(str(raw.get("title") or "").split())
    if not title or len(title) > 200:
        raise ValueError("Say what you finished.")
    kind = raw.get("type") if raw.get("type") in ("show", "course") else "show"
    try:
        day = datetime.date.fromisoformat(str(raw.get("date") or today.isoformat()))
    except ValueError:
        raise ValueError("That date isn't valid.")
    if day > today:
        raise ValueError("The date can't be in the future.")
    with LOCK:
        log = load_log(need_folder(settings), lang)
        mid = "finished-" + re.sub(r"\W+", "-", title.lower()).strip("-")
        if any(m.get("id") == mid for m in log["milestones"]):
            raise ValueError("\"%s\" is already marked finished." % title)
        log["milestones"].append({"id": mid, "kind": "finished", "type": kind, "title": title, "date": day.isoformat(),
                                  "label": "Finished %s" % title,
                                  "recorded": utc_stamp()})
        sync(settings, lang, today, log, save=True)
    return {"ok": True}


def unfinish(settings, lang, mid, today):
    """Take back a 'finished' mark made by mistake. Hours and word milestones can't be removed."""
    with LOCK:
        log = load_log(need_folder(settings), lang)
        kept = [m for m in log["milestones"] if not (m.get("id") == mid and m.get("kind") == "finished")]
        if len(kept) == len(log["milestones"]):
            raise ValueError("That can't be removed.")
        log["milestones"] = kept
        sync(settings, lang, today, log, save=True)
    return {"ok": True}


# ───────────────────────────── fast entry ─────────────────────────────
NUM_TAIL = re.compile(r"^(.*?)(\d+)$")


def next_title(title):
    """'Lesson 5' -> 'Lesson 6', 'S01E09' -> 'S01E10'. None if the title doesn't end in a number."""
    m = NUM_TAIL.match(title)
    if not m:
        return None
    head, num = m.groups()
    return head + str(int(num) + 1).zfill(len(num))


def series_key(title):
    m = NUM_TAIL.match(title)
    return " ".join(m.group(1).lower().split()) if m and m.group(1).strip() else None


def suggestions(entries):
    """What to offer: the next item of each recent series, and every remembered title."""
    have = {x["title"].lower() for x in entries}
    nxt, seen_series, titles, seen_titles = [], set(), [], set()
    for x in ordered(entries):
        low = x["title"].lower()
        if low not in seen_titles and len(titles) < REMEMBERED:
            seen_titles.add(low)
            titles.append({"title": x["title"], "type": x["type"], "minutes": x["minutes"]})
        key = None if x.get("link") else series_key(x["title"])      # a linked video has no "next one"
        if key and key not in seen_series:
            seen_series.add(key)
            t = next_title(x["title"])
            for _ in range(50):                      # skip ones already logged
                if t.lower() not in have:
                    break
                t = next_title(t)
            if len(nxt) < BUTTONS:
                nxt.append({"title": t, "type": x["type"], "minutes": x["minutes"], "after": x["title"]})
    return {"next": nxt, "titles": titles}


# ───────────────────────────── lookups ─────────────────────────────
YT_ID = re.compile(r"^[\w-]{11}$")
EPISODE = re.compile(r"^(.+?)[\s._\-–]*\b(?:S(\d{1,2})\s*E(\d{1,3})|(\d{1,2})x(\d{1,3}))$", re.I)
TMDB = "https://api.themoviedb.org/3"
LOOKUP_FAILED = "The lookup didn't work (%s). You can type the duration yourself."


def youtube_id(text):
    """The video id from a YouTube link, or None. Nothing else is ever fetched."""
    try:
        u = urlparse(str(text).strip())
        host = (u.hostname or "").lower()
    except ValueError:
        return None
    if u.scheme not in ("http", "https"):
        return None
    parts = [x for x in u.path.split("/") if x]
    if host == "youtu.be":
        vid = parts[0] if parts else ""
    elif host == "youtube.com" or host.endswith(".youtube.com"):
        if parts == ["watch"]:
            vid = (parse_qs(u.query).get("v") or [""])[0]
        elif len(parts) == 2 and parts[0] in ("shorts", "live", "embed"):
            vid = parts[1]
        else:
            return None
    else:
        return None
    return vid if YT_ID.match(vid) else None


def parse_youtube(page):
    """(title, seconds) from a YouTube watch page. Either may be None."""
    secs = None
    m = re.search(r'"lengthSeconds"\s*:\s*"?(\d+)', page)
    if m:
        secs = int(m.group(1))
    else:
        m = re.search(r'itemprop="duration"\s+content="PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?"', page)
        if m and any(m.groups()):
            h, mi, se = (int(g or 0) for g in m.groups())
            secs = h * 3600 + mi * 60 + se
    t = (re.search(r'<meta\s+property="og:title"\s+content="([^"]*)"', page)
         or re.search(r'<meta\s+name="title"\s+content="([^"]*)"', page))
    title = " ".join(html.unescape(t.group(1)).split()) if t else None
    return title or None, secs or None


CA_FILES = ["/etc/ssl/cert.pem", "/opt/homebrew/etc/ca-certificates/cert.pem", "/opt/homebrew/etc/openssl@3/cert.pem",
            "/usr/local/etc/openssl@3/cert.pem", "/etc/ssl/certs/ca-certificates.crt"]
GOOD_CONTEXT = []                 # the certificate set that worked last time
NO_CERTS = ("this Python can't check secure sites. On a Mac, open Applications > Python and run "
            "\"Install Certificates.command\", then try again")


def ssl_contexts():
    """Certificate sets to try, in order. Some Python installs on macOS ship with none of their own."""
    if GOOD_CONTEXT:
        yield GOOD_CONTEXT[0]
    yield ssl.create_default_context()
    files = []
    try:
        import certifi                # used only if it happens to be installed
        files.append(certifi.where())
    except Exception:
        pass
    for f in files + CA_FILES:
        if os.path.isfile(f):
            try:
                yield ssl.create_default_context(cafile=f)
            except (ssl.SSLError, OSError):
                pass


def http_get(url, headers=None, opener=urllib.request.urlopen):
    """Text of a page. Only ever called with youtube.com and themoviedb.org addresses built here."""
    req = urllib.request.Request(url, headers=dict({"User-Agent": "Mozilla/5.0 (PathToFluent Logbook)",
                                                    "Accept-Language": "en"}, **(headers or {})))
    for ctx in ssl_contexts():
        try:
            with opener(req, timeout=8, context=ctx) as r:
                text = r.read(4000000).decode("utf-8", "replace")
            GOOD_CONTEXT[:] = [ctx]
            return text
        except urllib.error.HTTPError as e:
            if e.code in (401, 403) and "themoviedb" in url:
                raise ValueError("TMDB rejected the key. Check it in Settings.")
            raise ValueError(LOOKUP_FAILED % ("the site answered %d" % e.code))
        except urllib.error.URLError as e:
            if isinstance(e.reason, ssl.SSLCertVerificationError):
                continue                               # try the next certificate set
            raise ValueError(LOOKUP_FAILED % ("no connection: %s" % (e.reason,)))
        except ssl.SSLCertVerificationError:
            continue
        except OSError as e:
            raise ValueError(LOOKUP_FAILED % ("no connection: %s" % (e,)))
    raise ValueError(LOOKUP_FAILED % NO_CERTS)


def minutes_of(seconds):
    return max(1, min(MAX_MINUTES, int(seconds / 60 + 0.5)))


def lookup_youtube(vid, get=http_get):
    link = "https://www.youtube.com/watch?v=" + vid
    title, secs = parse_youtube(get(link))
    if not secs:
        raise ValueError(LOOKUP_FAILED % "YouTube didn't give a length for that video")
    return {"source": "YouTube", "title": title or "", "minutes": minutes_of(secs), "link": link}


def tmdb_get(path, params, key, get=http_get):
    headers = {}
    if len(key) > 40:                               # long token = v4 "read access token"
        headers["Authorization"] = "Bearer " + key
    else:                                           # short key = v3 API key
        params = dict(params, api_key=key)
    try:
        return json.loads(get(TMDB + path + ("?" + urlencode(params) if params else ""), headers))
    except json.JSONDecodeError:
        raise ValueError(LOOKUP_FAILED % "TMDB sent something unexpected")


def lookup_episode(title, key, get=http_get):
    m = EPISODE.match(" ".join(title.split()))
    if not m:
        raise ValueError("Write the episode like this: Show name S01E02")
    show, season, episode = m.group(1).strip(), int(m.group(2) or m.group(4)), int(m.group(3) or m.group(5))
    found = tmdb_get("/search/tv", {"query": show}, key, get).get("results") or []
    if not found:
        raise ValueError("TMDB doesn't know a show called \"%s\"." % show)
    try:
        ep = tmdb_get("/tv/%d/season/%d/episode/%d" % (int(found[0]["id"]), season, episode), {}, key, get)
    except ValueError as e:
        if "404" in str(e):
            raise ValueError("TMDB has no S%02dE%02d for %s." % (season, episode, found[0].get("name") or show))
        raise
    runtime = ep.get("runtime")
    if not isinstance(runtime, int) or runtime < 1:
        raise ValueError("TMDB has no running time for that episode. You can type it yourself.")
    return {"source": "TMDB", "minutes": min(MAX_MINUTES, runtime), "show": found[0].get("name") or show}


def lookup(text, settings, get=http_get):
    """Fill in a duration from a YouTube link or a 'Show S01E02' title. Never signs in to anything."""
    if not settings.get("lookups", True):
        raise ValueError("Lookups are turned off in Settings.")
    text = str(text or "").strip()
    vid = youtube_id(text)
    if vid:
        return lookup_youtube(vid, get)
    if EPISODE.match(" ".join(text.split())):
        if not settings.get("tmdb_key"):
            raise ValueError("Add a TMDB key in Settings to look up episode lengths.")
        return lookup_episode(text, settings["tmdb_key"], get)
    raise ValueError("Logbook can look up YouTube links and titles like \"Show name S01E02\".")


# ───────────────────────────── actions ─────────────────────────────
def lang_ok(settings, lang):
    if not any(l["code"] == lang for l in settings["languages"]):
        raise ValueError("Unknown language.")
    return lang


def need_folder(settings):
    f = settings.get("folder") or ""
    if not f:
        raise ValueError("Choose a data folder first.")
    if not os.path.isdir(f):
        raise ValueError("The data folder can't be found: %s" % f)
    return f


def state(settings, lang, today):
    out = {"version": VERSION, "types": TYPES, "languages": settings["languages"], "lang": lang,
           "folder": settings.get("folder") or "", "today": today.isoformat(), "configured": False,
           "entries": [], "totals": None, "error": "", "suggest": {"next": [], "titles": []},
           "lookups": bool(settings.get("lookups", True)), "tmdb": bool(settings.get("tmdb_key")),
           "cards": {"numbers": None, "note": ""}, "stats_folder": settings.get("stats_folder") or "",
           "milestones": [], "progress": None, "finishable": []}
    try:
        folder = need_folder(settings)
    except ValueError as e:
        out["error"] = str(e) if settings.get("folder") else ""
        return out
    out["configured"] = True
    try:
        with LOCK:
            log, cards = sync(settings, lang, today)
    except LogError as e:
        out["error"] = str(e)
        return out
    except OSError as e:
        out["error"] = "Logbook can't write to the data folder: %s" % (e.strerror or e)
        return out
    out["entries"] = ordered(log["entries"])
    out["totals"] = totals(log["entries"], today, settings.get("week_start", 0))
    out["suggest"] = suggestions(log["entries"])
    out["cards"] = cards
    out["milestones"] = sorted(log["milestones"], key=lambda m: (m.get("date", ""), m.get("recorded", "")), reverse=True)
    out["progress"] = progress(log, cards["numbers"], today)
    done = {m.get("title", "").lower() for m in log["milestones"] if m.get("kind") == "finished"}
    out["finishable"] = [c for c in finished_candidates(log["entries"]) if c["title"].lower() not in done]
    return out


def add_entry(settings, lang, raw, today, again=False):
    folder = need_folder(settings)
    e = clean_entry(raw, today)
    with LOCK:
        log = load_log(folder, lang)
        if is_duplicate(log["entries"], e) and not again:
            return {"duplicate": True}
        e["id"] = uuid.uuid4().hex[:12]
        e["added"] = datetime.datetime.now().isoformat(timespec="seconds")
        log["entries"].append(e)
        sync(settings, lang, today, log, save=True)
    return {"ok": True, "id": e["id"]}


def edit_entry(settings, lang, entry_id, raw, today):
    folder = need_folder(settings)
    e = clean_entry(raw, today)
    with LOCK:
        log = load_log(folder, lang)
        for x in log["entries"]:
            if x.get("id") == entry_id:
                x.update(e)
                sync(settings, lang, today, log, save=True)
                return {"ok": True}
    raise ValueError("That entry no longer exists.")


def delete_entry(settings, lang, entry_id, today=None):
    folder = need_folder(settings)
    with LOCK:
        log = load_log(folder, lang)
        kept = [x for x in log["entries"] if x.get("id") != entry_id]
        if len(kept) == len(log["entries"]):
            raise ValueError("That entry no longer exists.")
        log["entries"] = kept
        sync(settings, lang, today or datetime.date.today(), log, save=True)
    return {"ok": True}


def set_folder(settings, path):
    path = os.path.abspath(os.path.expanduser(str(path or "").strip()))
    if not os.path.isdir(path):
        raise ValueError("That folder doesn't exist: %s" % path)
    if not os.access(path, os.W_OK):
        raise ValueError("Logbook can't write to that folder.")
    settings["folder"] = path
    save_settings(settings)
    return {"ok": True}


def set_options(settings, req):
    if "lookups" in req:
        settings["lookups"] = bool(req["lookups"])
    if "stats_folder" in req:
        f = str(req["stats_folder"] or "").strip()
        if f:
            f = os.path.abspath(os.path.expanduser(f))
            if not os.path.isdir(f):
                raise ValueError("That folder doesn't exist: %s" % f)
        settings["stats_folder"] = f
    if "tmdb_key" in req:
        key = str(req["tmdb_key"] or "").strip()
        if key and not re.match(r"^[\w.\-]{20,400}$", key):
            raise ValueError("That doesn't look like a TMDB key.")
        settings["tmdb_key"] = key
    save_settings(settings)
    return {"ok": True}


def list_dir(path):
    home = os.path.expanduser("~")
    path = os.path.abspath(os.path.expanduser(path or home))
    if not os.path.isdir(path):
        path = home
    dirs = []
    try:
        for e in os.scandir(path):
            try:
                if not e.name.startswith(".") and e.is_dir():
                    dirs.append(e.name)
            except OSError:
                pass
    except OSError as err:
        raise ValueError("Can't open that folder: %s" % err.strerror)
    places = [{"name": "Home", "path": home}]
    for n in ("Documents", "Desktop"):
        if os.path.isdir(os.path.join(home, n)):
            places.append({"name": n, "path": os.path.join(home, n)})
    if sys.platform == "darwin" and os.path.isdir("/Volumes"):
        places.append({"name": "Drives", "path": "/Volumes"})
    if os.name == "nt":
        places += [{"name": d + ":", "path": d + ":\\"} for d in string.ascii_uppercase if os.path.isdir(d + ":\\")]
    return {"path": path, "parent": os.path.dirname(path) or path, "sep": os.sep,
            "dirs": sorted(dirs, key=str.lower), "places": places}


# ───────────────────────────── web server ─────────────────────────────
class Handler(BaseHTTPRequestHandler):
    server_version = APP

    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype="application/json"):
        if isinstance(body, (dict, list)):
            body = json.dumps(body).encode("utf-8")
        elif isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _ok(self):
        host = (self.headers.get("Host") or "").split(":")[0]
        if host not in ("127.0.0.1", "localhost"):
            return False
        return secrets.compare_digest(self.headers.get("X-Token") or "", TOKEN)

    def do_GET(self):
        u = urlparse(self.path)
        q = parse_qs(u.query)
        if u.path == "/":
            return self._send(200, PAGE.replace("__TOKEN__", TOKEN), "text/html; charset=utf-8")
        if not u.path.startswith("/api/") or not self._ok():
            return self._send(403, {"error": "Forbidden"})
        g = lambda k, d="": (q.get(k) or [d])[0]
        try:
            s = load_settings()
            if u.path == "/api/state":
                lang = g("lang") or s["languages"][0]["code"]
                return self._send(200, state(s, lang_ok(s, lang), datetime.date.today()))
            if u.path == "/api/ls":
                return self._send(200, list_dir(g("path")))
            if u.path == "/api/lookup":
                return self._send(200, lookup(g("q"), s))
            self._send(404, {"error": "Not found"})
        except Exception as e:
            self._send(400, {"error": str(e) or e.__class__.__name__})

    def do_POST(self):
        u = urlparse(self.path)
        if not u.path.startswith("/api/") or not self._ok():
            return self._send(403, {"error": "Forbidden"})
        try:
            n = int(self.headers.get("Content-Length") or 0)
            if n > 100000:
                raise ValueError("Too much data.")
            req = json.loads(self.rfile.read(n).decode("utf-8") or "{}")
            s = load_settings()
            today = datetime.date.today()
            if u.path == "/api/folder":
                return self._send(200, set_folder(s, req.get("path")))
            if u.path == "/api/settings":
                return self._send(200, set_options(s, req))
            if u.path == "/api/quit":
                self._send(200, {"ok": True})
                return threading.Thread(target=self.server.shutdown, daemon=True).start()
            lang = lang_ok(s, req.get("lang") or s["languages"][0]["code"])
            if u.path == "/api/add":
                return self._send(200, add_entry(s, lang, req.get("entry") or {}, today, bool(req.get("again"))))
            if u.path == "/api/edit":
                return self._send(200, edit_entry(s, lang, req.get("id"), req.get("entry") or {}, today))
            if u.path == "/api/delete":
                return self._send(200, delete_entry(s, lang, req.get("id"), today))
            if u.path == "/api/finish":
                return self._send(200, finish(s, lang, req, today))
            if u.path == "/api/unfinish":
                return self._send(200, unfinish(s, lang, req.get("id"), today))
            self._send(404, {"error": "Not found"})
        except Exception as e:
            self._send(400, {"error": str(e) or e.__class__.__name__})


# ───────────────────────────── interface ─────────────────────────────
PAGE = r"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>PathToFluent Logbook</title>
<style>
:root{--bg:#f4f4f1;--card:#fff;--ink:#1d1d1f;--mute:#6b6b70;--line:#e2e2dd;--acc:#2f6f5e;--acc2:#e7f1ee;--bad:#b3261e}
@media(prefers-color-scheme:dark){:root{--bg:#161617;--card:#212123;--ink:#ececec;--mute:#9a9aa0;--line:#333336;--acc:#6fc3ab;--acc2:#23332f;--bad:#ff8a80}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 -apple-system,"Segoe UI",Roboto,Helvetica,Arial,sans-serif}
header{display:flex;align-items:center;gap:12px;padding:18px 28px}header h1{font-size:20px;margin:0;letter-spacing:-.01em}
header span{color:var(--mute);font-size:13px;flex:1}main{max-width:960px;margin:0 auto;padding:0 20px 80px}
section{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:22px 24px;margin-bottom:18px}
section h2{margin:0 0 4px;font-size:16px}.hint{color:var(--mute);font-size:13px;margin:0 0 14px}
.row{display:flex;gap:10px;align-items:center;margin:10px 0;flex-wrap:wrap}
label{font-size:13px;color:var(--mute)}.f{display:flex;flex-direction:column;gap:4px}.f.grow{flex:1;min-width:220px}
input,select{font:inherit;color:inherit;background:var(--bg);border:1px solid var(--line);border-radius:8px;padding:8px 10px}
input[type=number]{width:110px}input:focus,select:focus{outline:2px solid var(--acc);outline-offset:-1px}
button{font:inherit;border-radius:8px;border:1px solid var(--line);background:var(--card);color:inherit;padding:8px 14px;cursor:pointer}
button:hover{border-color:var(--acc)}button.primary{background:var(--acc);border-color:var(--acc);color:var(--card);font-weight:600}
button.small{padding:3px 10px;font-size:13px}button.bad:hover{border-color:var(--bad);color:var(--bad)}
.err{color:var(--bad);font-size:13px;white-space:pre-wrap}.hide{display:none!important}
.tiles{display:grid;grid-template-columns:repeat(4,1fr);gap:12px}@media(max-width:720px){.tiles{grid-template-columns:repeat(2,1fr)}}
.tile{background:var(--bg);border-radius:10px;padding:12px 14px}.tile b{display:block;font-size:22px;letter-spacing:-.01em;font-variant-numeric:tabular-nums}
.tile small{color:var(--mute);font-size:12px}.tile .parts{color:var(--mute);font-size:12px;margin-top:4px}
table{border-collapse:collapse;width:100%;font-size:14px}th{text-align:left;font-size:12px;color:var(--mute);font-weight:500;padding:8px;border-bottom:1px solid var(--line)}
td{padding:8px;border-bottom:1px solid var(--line);vertical-align:top}td.n{font-variant-numeric:tabular-nums;white-space:nowrap}
td.act{white-space:nowrap;text-align:right}tr.cur td{background:var(--acc2)}.note{color:var(--mute);font-size:13px}
.tag{font-size:12px;border:1px solid var(--line);border-radius:999px;padding:1px 9px;color:var(--mute);white-space:nowrap}
.empty{color:var(--mute);padding:18px 8px}details{margin-top:10px}summary{cursor:pointer;color:var(--mute);font-size:13px}
.mile{display:flex;gap:12px;align-items:baseline;padding:7px 0;border-bottom:1px solid var(--line)}.mile .when{color:var(--mute);font-size:13px;min-width:130px}.mile .what{flex:1;font-weight:600}.mute{color:var(--mute);font-size:13px}
#nextup button{border-radius:999px;padding:5px 14px;font-size:14px}#nextup button small{color:var(--mute)}.opt{display:flex;gap:8px;align-items:center;font-size:15px;color:var(--ink)}
dialog{border:1px solid var(--line);border-radius:14px;background:var(--card);color:var(--ink);padding:0;width:min(600px,94vw)}
dialog::backdrop{background:#0006}.dlg{padding:18px 20px}.places{display:flex;gap:6px;flex-wrap:wrap;margin:10px 0}
.places button{padding:4px 10px;font-size:13px;border-radius:999px}.path{font-size:12px;color:var(--mute);word-break:break-all}
.list{height:300px;overflow:auto;border:1px solid var(--line);border-radius:10px;margin:10px 0}
.list div{padding:7px 12px;cursor:pointer;border-bottom:1px solid var(--line);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.list div:hover{background:var(--acc2)}.list .e{color:var(--mute);cursor:default}
</style></head><body>
<header><h1>PathToFluent Logbook</h1><span>Your time with the language</span>
<select id="lang" class="hide" aria-label="Language"></select><button id="bset">Settings…</button><button id="quit">Quit</button></header>
<main>
<section id="setup" class="hide"><h2>Choose where to keep your log</h2>
<p class="hint">Logbook saves everything as plain files in one folder. Pick any folder you like; you can change it later.</p>
<div class="row"><button id="bsetup" class="primary">Choose a folder…</button></div></section>

<section id="broken" class="hide"><h2>The log can't be opened</h2><p class="err" id="brokenmsg"></p></section>

<section id="addbox"><h2 id="formtitle">Log a session</h2><p class="hint">What did you watch, listen to, read or practise?</p>
<div class="row hide" id="nextup"></div>
<form id="form" autocomplete="off" novalidate>
<div class="row"><div class="f grow"><label for="title">What</label><input id="title" maxlength="500" list="titles" placeholder="El crimen de Pazos S01E02, Pimsleur Lesson 5, or a YouTube link"><datalist id="titles"></datalist></div>
<div class="f"><label for="type">Type</label><select id="type"></select></div>
<div class="f"><label for="minutes">Minutes</label><input id="minutes" type="number" min="1" max="1440" inputmode="numeric"></div>
<div class="f"><label>&nbsp;</label><button type="button" id="blook" title="Fill in the duration from a YouTube link or an episode title">Look up</button></div>
<div class="f"><label for="date">Date</label><input id="date" type="date"></div></div>
<div class="row"><div class="f grow"><label for="note">Note (optional)</label><input id="note" maxlength="500"></div>
<div class="f grow"><label for="link">Link (optional)</label><input id="link" maxlength="500" placeholder="https://"></div></div>
<div class="row"><button class="primary" id="save" type="submit">Add to log</button><button type="button" id="clear">Clear</button><button type="button" id="cancel" class="hide">Cancel</button><span class="err" id="formerr" role="alert"></span><span class="mute" id="looknote" role="status"></span></div>
</form></section>

<section id="totalsbox"><h2>Totals</h2><p class="hint" id="weekhint"></p><div class="tiles" id="tiles"></div></section>

<section id="cardsbox"><h2>Cards</h2><p class="hint" id="cardshint"></p><div class="tiles" id="cardtiles"></div></section>

<section id="milebox"><h2>Milestones</h2><p class="hint" id="milehint"></p><div id="miles"></div>
<details><summary>Mark a show or course as finished</summary>
<div class="row"><div class="f grow"><label for="fintitle">What did you finish?</label><input id="fintitle" maxlength="200" list="finlist"><datalist id="finlist"></datalist></div>
<div class="f"><label for="fintype">Type</label><select id="fintype"><option value="show">Show</option><option value="course">Course</option></select></div>
<div class="f"><label for="findate">Date</label><input id="findate" type="date"></div>
<div class="f"><label>&nbsp;</label><button id="finsave" type="button">Mark finished</button></div></div><span class="err" id="finerr" role="alert"></span></details></section>

<section id="listbox"><h2>Entries</h2><div id="entries"></div></section>
</main>
<dialog id="fb"><div class="dlg"><b>Choose a folder</b><div class="places" id="fbplaces"></div><div class="path" id="fbpath"></div>
<div class="list" id="fblist"></div><div class="row" style="justify-content:flex-end"><span class="err" id="fberr" style="flex:1"></span><button id="fbpick" class="primary">Use this folder</button><button id="fbclose">Cancel</button></div></div></dialog>
<dialog id="set"><div class="dlg"><b>Settings</b>
<div class="row"><div class="f grow"><label>Data folder</label><div class="path" id="setfolder"></div></div><button id="bfolder">Change…</button></div>
<div class="row"><div class="f grow"><label>Card numbers from Waypoint: folder holding waypoint_stats.json</label><div class="path" id="setstats"></div></div><button id="bstats">Change…</button><button id="bstatsreset">Use the data folder</button></div>
<div class="row"><label class="opt"><input type="checkbox" id="lookups"> Fill in durations from YouTube links and episode titles</label></div>
<div class="row"><div class="f grow"><label for="tmdb">TMDB key, for episode lengths (optional, free at themoviedb.org → Settings → API)</label><input id="tmdb" type="password" autocomplete="off" spellcheck="false"></div></div>
<p class="mute" id="tmdbstate"></p>
<div class="row" style="justify-content:flex-end"><span class="err" id="seterr" style="flex:1"></span><button id="setsave" class="primary">Save</button><button id="setclose">Close</button></div></div></dialog>
<script>
const T="__TOKEN__",$=s=>document.querySelector(s);let S=null,editing=null,lang="";
async function api(path,body){const o={headers:{"X-Token":T}};if(body){o.method="POST";o.body=JSON.stringify(body);o.headers["Content-Type"]="application/json"}
  const r=await fetch(path,o),d=await r.json().catch(()=>({error:"No answer from Logbook. Is it still running?"}));if(!r.ok)throw new Error(d.error||"Something went wrong.");return d}
const el=(tag,cls,text)=>{const e=document.createElement(tag);if(cls)e.className=cls;if(text!=null)e.textContent=text;return e};
const dur=m=>{const h=Math.floor(m/60),r=m%60;return h?(r?h+" h "+r+" min":h+" h"):r+" min"};
const nice=d=>new Date(d+"T12:00:00").toLocaleDateString(undefined,{weekday:"short",day:"numeric",month:"short",year:"numeric"});
const cap=s=>s[0].toUpperCase()+s.slice(1);
function show(id,on){$(id).classList.toggle("hide",!on)}
async function load(){try{S=await api("/api/state?lang="+encodeURIComponent(lang))}catch(e){$("#formerr").textContent=e.message;return}
  lang=S.lang;const ls=$("#lang");ls.replaceChildren(...S.languages.map(l=>{const o=el("option",null,l.name);o.value=l.code;return o}));ls.value=lang;show("#lang",S.languages.length>1);
  const broken=S.configured&&S.error;show("#setup",!S.configured);show("#broken",!!broken);$("#brokenmsg").textContent=broken?S.error:"";
  const ready=S.configured&&!S.error;["#addbox","#totalsbox","#cardsbox","#milebox","#listbox"].forEach(i=>show(i,ready));
  if(!S.configured&&S.error)$("#setup .hint").textContent=S.error+" Choose a folder to carry on.";
  if(!ready)return;
  if(!$("#type").options.length)$("#type").replaceChildren(...S.types.map(t=>{const o=el("option",null,cap(t));o.value=t;return o}));
  $("#date").max=S.today;if(!$("#date").value)$("#date").value=S.today;
  tiles();cards();miles();list();nextup()}
function miles(){const box=$("#miles"),p=S.progress,bits=[];box.replaceChildren();
  if(p){bits.push(dur(p.minutes_to_go)+" to "+p.hours_next.toLocaleString()+" hours");if(p.words_next)bits.push(p.words_to_go.toLocaleString()+" words to "+p.words_next.toLocaleString()+" known words")}
  $("#milehint").textContent=bits.length?"Next: "+bits.join(" · ")+".":"";
  if(!S.milestones.length)box.append(el("div","empty","None yet. The first one is at 10 hours."));
  S.milestones.forEach(m=>{const r=el("div","mile");r.append(el("span","when",nice(m.date)),el("span","what",m.label));
    if(m.kind=="finished"){const b=el("button","small bad","Remove");b.onclick=()=>unfin(m);r.append(b)}box.append(r)});
  $("#finlist").replaceChildren(...S.finishable.map(c=>{const o=el("option");o.value=c.title;return o}));$("#findate").max=S.today;if(!$("#findate").value)$("#findate").value=S.today}
$("#fintitle").addEventListener("change",()=>{const c=S.finishable.find(c=>c.title.toLowerCase()==$("#fintitle").value.trim().toLowerCase());if(c)$("#fintype").value=c.type});
$("#finsave").onclick=async()=>{$("#finerr").textContent="";try{await api("/api/finish",{lang,title:$("#fintitle").value,type:$("#fintype").value,date:$("#findate").value});$("#fintitle").value="";await load()}catch(e){$("#finerr").textContent=e.message}};
async function unfin(m){if(!confirm('Remove "'+m.label+'" from your milestones?'))return;try{await api("/api/unfinish",{lang,id:m.id});await load()}catch(e){$("#finerr").textContent=e.message}}
function cards(){const c=S.cards,n=c.numbers,box=$("#cardtiles");box.replaceChildren();
  if(!n){$("#cardshint").textContent=c.note||"No card numbers yet. In Anki, choose a \"Daily numbers folder\" in PathToFluent Waypoint's settings, then reconcile.";return}
  const f=v=>v==null?"–":v.toLocaleString(),ch=(v,d)=>v==null?"":(v>0?"+":"")+v.toLocaleString()+" in "+d+" days";
  $("#cardshint").textContent="From Waypoint, last updated "+nice(n.date)+". Not counted in your hours.";
  [["Known words",n.known_words,[ch(n.change7,7),ch(n.change30,30)].filter(Boolean).join(" · ")||"Changes show after a week"],["Words being learned",n.learning_words,""],
   ["Cards studied",n.cards_studied,"so far"],["Cards waiting",n.cards_waiting,"held until they have one new word"]].forEach(([name,v,sub])=>{
    const d=el("div","tile");d.append(el("small",null,name),el("b",null,f(v)),el("div","parts",sub));box.append(d)})}
const isYT=v=>/^https?:\/\/([a-z]+\.)?(youtube\.com|youtu\.be)\//i.test(v.trim()),isEp=v=>/\b(S\d{1,2}\s*E\d{1,3}|\d{1,2}x\d{1,3})$/i.test(v.trim());let pending=null;
function note(t){$("#looknote").textContent=t||""}
function nextup(){const box=$("#nextup"),n=S.suggest.next;show("#nextup",n.length>0&&!editing);
  box.replaceChildren(el("span","mute","Next up:"),...n.map(x=>{const b=el("button");b.type="button";b.append(x.title+" ",el("small",null,"· "+dur(x.minutes)));b.onclick=()=>useNext(x);return b}));
  $("#titles").replaceChildren(...n.concat(S.suggest.titles).map(x=>{const o=el("option");o.value=x.title;return o}))}
async function useNext(x){$("#title").value=x.title;$("#type").value=x.type;$("#minutes").value=x.minutes;$("#date").value=S.today;$("#formerr").textContent="";note("");
  if(S.lookups&&S.tmdb&&isEp(x.title))await find(x.title,true);$("#save").focus()}
function find(q,replace){pending=find1(q,replace).finally(()=>{pending=null});return pending}
async function find1(q,replace){note("Looking it up…");try{const r=await api("/api/lookup?q="+encodeURIComponent(q));
    if(r.title&&!$("#title").value.trim())$("#title").value=r.title;if(r.link)$("#link").value=r.link;
    if(r.minutes&&(replace||!$("#minutes").value.trim()))$("#minutes").value=r.minutes;
    note("Filled in from "+r.source+(r.show?" ("+r.show+")":"")+": "+dur(r.minutes)+". Change it if it's wrong.")}catch(e){note(e.message)}}
$("#title").addEventListener("change",async()=>{const v=$("#title").value.trim();if(!v||!S)return;note("");
  if(isYT(v)){if(S.lookups){$("#title").value="";$("#link").value=v;await find(v,true)}return}
  const known=S.suggest.next.concat(S.suggest.titles).find(x=>x.title.toLowerCase()==v.toLowerCase());
  if(known&&!editing){$("#type").value=known.type;if(!$("#minutes").value.trim())$("#minutes").value=known.minutes}
  if(S.lookups&&isEp(v)&&(!known||!S.suggest.titles.includes(known))){if(S.tmdb)await find(v,!!known);else note("Add a TMDB key in Settings to fill in episode lengths.")}});
$("#blook").onclick=()=>{const l=$("#link").value.trim(),t=$("#title").value.trim();
  if(!S.lookups)return note("Lookups are turned off in Settings.");
  if(isYT(l))return find(l,true);if(isYT(t)){$("#title").value="";$("#link").value=t;return find(t,true)}
  if(isEp(t))return S.tmdb?find(t,true):note("Add a TMDB key in Settings to fill in episode lengths.");
  note('Logbook can look up a YouTube link, or a title written like "Show name S01E02".')};
$("#clear").onclick=()=>{["#title","#minutes","#note","#link"].forEach(i=>$(i).value="");if(!editing)$("#date").value=S.today;$("#formerr").textContent="";note("");$("#title").focus()};
$("#link").addEventListener("change",()=>{const v=$("#link").value.trim();if(S&&S.lookups&&isYT(v))find(v,false)});
function tiles(){const t=S.totals,box=$("#tiles");box.replaceChildren();
  const parts=o=>Object.entries(o.by_type).sort((a,b)=>b[1]-a[1]).map(([k,v])=>cap(k)+" "+dur(v)).join(" · ");
  [["This week",t.week],["This month",t.month],["All time",t.all]].forEach(([name,o])=>{const d=el("div","tile");d.append(el("small",null,name),el("b",null,dur(o.minutes)),el("div","parts",parts(o)||"Nothing yet"));box.append(d)});
  const d=el("div","tile");d.append(el("small",null,"Streak"),el("b",null,t.streak+(t.streak==1?" day":" days")),el("div","parts",t.entries+(t.entries==1?" entry":" entries")+" in all"));box.append(d);
  $("#weekhint").textContent="The week started on "+nice(t.week_from)+"."}
function list(){const box=$("#entries");box.replaceChildren();
  if(!S.entries.length){box.append(el("div","empty","No entries yet. Log your first session above."));return}
  const tb=el("table"),head=el("tr");["Date","What","Type","Time",""].forEach(h=>head.append(el("th",null,h)));tb.append(head);
  S.entries.forEach(e=>{const tr=el("tr",editing==e.id?"cur":"");const what=el("td");what.append(el("div",null,e.title));
    if(e.note)what.append(el("div","note",e.note));
    if(e.link){const a=el("a","note",e.link.replace(/^https?:\/\//,"").slice(0,60));a.href=e.link;a.target="_blank";a.rel="noopener noreferrer";what.append(a)}
    const ty=el("td");ty.append(el("span","tag",cap(e.type)));const act=el("td","act");
    const be=el("button","small","Edit");be.onclick=()=>startEdit(e);const bd=el("button","small bad","Delete");bd.onclick=()=>del(e);act.append(be," ",bd);
    tr.append(el("td","n",nice(e.date)),what,ty,el("td","n",dur(e.minutes)),act);tb.append(tr)});box.append(tb)}
function formData(){return{title:$("#title").value,type:$("#type").value,minutes:$("#minutes").value.trim(),date:$("#date").value,note:$("#note").value,link:$("#link").value}}
function resetForm(){editing=null;note("");["#title","#minutes","#note","#link"].forEach(i=>$(i).value="");$("#date").value=S.today;$("#formtitle").textContent="Log a session";$("#save").textContent="Add to log";show("#cancel",false);$("#formerr").textContent=""}
function startEdit(e){editing=e.id;$("#title").value=e.title;$("#type").value=e.type;$("#minutes").value=e.minutes;$("#date").value=e.date;$("#note").value=e.note||"";$("#link").value=e.link||"";
  $("#formtitle").textContent="Change an entry";$("#save").textContent="Save changes";show("#cancel",true);$("#formerr").textContent="";note("");show("#nextup",false);list();$("#title").focus();window.scrollTo({top:0,behavior:"smooth"})}
$("#cancel").onclick=()=>{resetForm();list();nextup()};
$("#form").onsubmit=async ev=>{ev.preventDefault();$("#formerr").textContent="";if(pending)await pending;const entry=formData();
  try{if(editing){await api("/api/edit",{lang,id:editing,entry})}
    else{let r=await api("/api/add",{lang,entry});
      if(r.duplicate){if(!confirm("You already logged this, with the same date and duration. Log it again?"))return;r=await api("/api/add",{lang,entry,again:true})}}
    resetForm();await load();$("#title").focus()}catch(e){$("#formerr").textContent=e.message}};
async function del(e){if(!confirm('Delete "'+e.title+'" ('+dur(e.minutes)+", "+nice(e.date)+")?"))return;
  try{await api("/api/delete",{lang,id:e.id});if(editing==e.id)resetForm();await load()}catch(x){$("#formerr").textContent=x.message}}
$("#lang").onchange=e=>{lang=e.target.value;resetForm();load()};
async function ls(p){$("#fberr").textContent="";let d;try{d=await api("/api/ls?path="+encodeURIComponent(p||""))}catch(e){$("#fberr").textContent=e.message;return}
  $("#fbpath").textContent=d.path;$("#fb").dataset.path=d.path;
  $("#fbplaces").replaceChildren(...d.places.map(pl=>{const b=el("button",null,pl.name);b.onclick=()=>ls(pl.path);return b}));
  const L=$("#fblist");L.replaceChildren();const add=(cls,text,fn)=>{const x=el("div",cls,text);if(fn)x.onclick=fn;L.append(x)};
  if(d.parent!=d.path)add("","↑  Up one folder",()=>ls(d.parent));
  d.dirs.forEach(n=>add("",n,()=>ls(d.path+(d.path.endsWith(d.sep)?"":d.sep)+n)));if(!d.dirs.length)add("e","No sub-folders here")}
let fbFor="data";const pick=()=>{fbFor="data";ls(S&&S.folder);$("#fb").showModal()};$("#bfolder").onclick=()=>{$("#set").close();pick()};$("#bsetup").onclick=pick;
$("#bstats").onclick=()=>{$("#set").close();fbFor="stats";ls(S.stats_folder||S.folder);$("#fb").showModal()};
$("#bstatsreset").onclick=async()=>{try{await api("/api/settings",{stats_folder:""});$("#set").close();await load()}catch(e){$("#seterr").textContent=e.message}};
$("#bset").onclick=()=>{$("#setfolder").textContent=S.folder||"Not chosen yet";$("#setstats").textContent=S.stats_folder||"The data folder";$("#lookups").checked=S.lookups;$("#tmdb").value="";$("#seterr").textContent="";
  $("#tmdbstate").textContent=S.tmdb?"A TMDB key is saved. Leave the box empty to keep it, or paste a new one.":"No TMDB key saved. Without one, type episode lengths yourself.";$("#set").showModal()};
$("#setclose").onclick=()=>$("#set").close();
$("#setsave").onclick=async()=>{const b={lookups:$("#lookups").checked},k=$("#tmdb").value.trim();if(k)b.tmdb_key=k;
  try{await api("/api/settings",b);$("#set").close();await load()}catch(e){$("#seterr").textContent=e.message}};$("#fbclose").onclick=()=>$("#fb").close();
$("#fbpick").onclick=async()=>{try{if(fbFor=="stats")await api("/api/settings",{stats_folder:$("#fb").dataset.path});else await api("/api/folder",{path:$("#fb").dataset.path});$("#fb").close();await load()}catch(e){$("#fberr").textContent=e.message}};
$("#quit").onclick=async()=>{if(!confirm("Quit Logbook?"))return;await api("/api/quit",{x:1}).catch(()=>{});document.body.replaceChildren(el("p",null,"Logbook has stopped. You can close this tab."));document.body.style.padding="40px"};
load();
</script></body></html>"""


def command_line(args):
    """--summary and --mark-used: bring the summary files up to date without opening the page."""
    s = load_settings()
    if args.folder:
        s["folder"] = os.path.abspath(os.path.expanduser(args.folder))
        names = os.listdir(s["folder"]) if os.path.isdir(s["folder"]) else []
        found = sorted(m.group(1) for m in (re.match(r"logbook-([a-z]{2,8})\.json$", n) for n in names) if m)
        known = {l["code"] for l in s["languages"]}
        s["languages"] += [{"code": c, "name": c} for c in found if c not in known]
    folder = need_folder(s)
    langs = [args.lang] if args.lang else [l["code"] for l in s["languages"] if os.path.exists(log_path(folder, l["code"]))]
    if not langs:
        print("No log found in that folder.")
        return 1
    today = datetime.date.today()
    for lang in langs:
        lang_ok(s, lang)
        with LOCK:
            if args.mark_used:
                print("%s: summary marked as used at %s" % (lang, mark_used(folder, lang)))
            log, cards = sync(s, lang, today)
        t = totals(log["entries"], today, s.get("week_start", 0))
        print("%s: %d min this week, %d min in all, %d milestone(s). Summary: %s" % (
            lang, t["week"]["minutes"], t["all"]["minutes"], len(log["milestones"]),
            os.path.basename(summary_path(folder, lang))))
    return 0


def main():
    ap = argparse.ArgumentParser(description="Logbook - keep a log of your time with a language")
    ap.add_argument("--port", type=int, default=8778)
    ap.add_argument("--no-browser", action="store_true", help="don't open the browser automatically")
    ap.add_argument("--summary", action="store_true", help="update the summary file(s) and exit, without opening the page")
    ap.add_argument("--mark-used", action="store_true", help="note that the summary was used for a post, then update it")
    ap.add_argument("--folder", help="data folder to use for --summary / --mark-used (default: the one in settings)")
    ap.add_argument("--lang", help="language code for --summary / --mark-used (default: every log in the folder)")
    args = ap.parse_args()
    if args.summary or args.mark_used:
        try:
            sys.exit(command_line(args))
        except (ValueError, LogError, OSError) as e:
            sys.exit("Logbook: %s" % e)
    try:
        httpd = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    except OSError:
        httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    url = "http://127.0.0.1:%d/" % httpd.server_address[1]
    print("%s %s is running at %s\nLeave this window open while you use it. Press Ctrl+C to quit." % (APP, VERSION, url))
    if not args.no_browser:
        threading.Timer(0.4, webbrowser.open, args=(url,)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    print("\n%s stopped." % APP)


if __name__ == "__main__":
    main()
