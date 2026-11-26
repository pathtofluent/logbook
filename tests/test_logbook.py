"""Tests for Logbook's rules. Run: python3 tests/test_logbook.py"""
import datetime, json, os, sys, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import logbook as lb

D = datetime.date
TODAY = D(2026, 11, 26)          # a Thursday
E = lambda title="Pimsleur Spanish L1 Lesson 5", kind="course", minutes=30, date=None, **kw: dict(
    title=title, type=kind, minutes=minutes, date=date or TODAY.isoformat(), **kw)


def settings(folder):
    return {"folder": folder, "languages": [{"code": "es", "name": "Spanish"}, {"code": "fr", "name": "French"}],
            "week_start": 0}


def raises(fn, text=""):
    try:
        fn()
    except (ValueError, lb.LogError) as e:
        assert text.lower() in str(e).lower(), str(e)
        return True
    raise AssertionError("expected an error")


def test_example_1_entry_saved_and_totals_rise():
    with tempfile.TemporaryDirectory() as d:
        s = settings(d)
        assert lb.add_entry(s, "es", E(), TODAY)["ok"]
        st = lb.state(s, "es", TODAY)
        assert st["entries"][0]["title"] == "Pimsleur Spanish L1 Lesson 5"
        assert st["entries"][0]["date"] == "2026-11-26"
        assert st["totals"]["week"]["minutes"] == 30 and st["totals"]["all"]["minutes"] == 30
        assert st["totals"]["all"]["by_type"] == {"course": 30}


def test_example_4_bad_durations_refused_nothing_saved():
    with tempfile.TemporaryDirectory() as d:
        s = settings(d)
        for bad in (0, "", None, -5, 1441, "abc", 2.5, True):
            raises(lambda: lb.add_entry(s, "es", E(minutes=bad), TODAY))
        assert not os.path.exists(lb.log_path(d, "es"))
        assert lb.add_entry(s, "es", E(minutes="45"), TODAY)["ok"]      # typed digits are fine
        assert lb.add_entry(s, "es", E(title="Long day", minutes=1440), TODAY)["ok"]


def test_example_5_duplicate_asks_first():
    with tempfile.TemporaryDirectory() as d:
        s = settings(d)
        lb.add_entry(s, "es", E(), TODAY)
        assert lb.add_entry(s, "es", E(title="pimsleur spanish l1 lesson 5"), TODAY) == {"duplicate": True}
        assert len(lb.load_log(d, "es")["entries"]) == 1
        assert lb.add_entry(s, "es", E(), TODAY, again=True)["ok"]
        assert len(lb.load_log(d, "es")["entries"]) == 2
        assert lb.add_entry(s, "es", E(minutes=31), TODAY)["ok"]        # different duration: no question


def test_example_10_streak():
    days = lambda *n: [{"date": D(2026, 11, x).isoformat(), "minutes": 10, "type": "show"} for x in n]
    assert lb.streak(days(23, 24, 25, 27), D(2026, 11, 27)) == 1        # Mon Tue Wed, skip Thu, Fri
    assert lb.streak(days(23, 24, 25), D(2026, 11, 25)) == 3
    assert lb.streak(days(23, 24, 25), D(2026, 11, 26)) == 3            # still alive the day after
    assert lb.streak(days(23, 24, 25), D(2026, 11, 27)) == 0
    assert lb.streak([], TODAY) == 0


def test_example_11_future_date_refused_past_allowed():
    raises(lambda: lb.clean_entry(E(date="2026-11-27"), TODAY), "future")
    assert lb.clean_entry(E(date="2025-01-01"), TODAY)["date"] == "2025-01-01"
    assert lb.clean_entry(dict(title="x", type="show", minutes=5), TODAY)["date"] == "2026-11-26"
    raises(lambda: lb.clean_entry(E(date="26/11/2026"), TODAY), "date")


def test_example_12_damaged_log_is_never_overwritten():
    with tempfile.TemporaryDirectory() as d:
        s = settings(d)
        lb.add_entry(s, "es", E(), TODAY)
        lb.add_entry(s, "es", E(title="Other"), TODAY)                  # makes a backup
        with open(lb.log_path(d, "es"), "w") as f:
            f.write("{ this is not json")
        raises(lambda: lb.add_entry(s, "es", E(title="New"), TODAY), "logbook-es.json")
        raises(lambda: lb.load_log(d, "es"), "newest backup is logbook-es-")
        assert open(lb.log_path(d, "es")).read() == "{ this is not json"
        st = lb.state(s, "es", TODAY)
        assert st["error"] and st["entries"] == [] and st["totals"] is None
        with open(lb.log_path(d, "es"), "w") as f:
            json.dump({"entries": [{"title": "no date or minutes"}]}, f)
        raises(lambda: lb.load_log(d, "es"), "can't be read")


def test_example_15_one_log_per_language():
    with tempfile.TemporaryDirectory() as d:
        s = settings(d)
        lb.add_entry(s, "es", E(), TODAY)
        lb.add_entry(s, "fr", E(title="Pimsleur French L1 Lesson 1"), TODAY)
        assert os.path.exists(os.path.join(d, "logbook-fr.json"))
        assert lb.state(s, "es", TODAY)["totals"]["all"]["minutes"] == 30
        assert [e["title"] for e in lb.state(s, "fr", TODAY)["entries"]] == ["Pimsleur French L1 Lesson 1"]
        raises(lambda: lb.lang_ok(s, "de"), "language")


def test_totals_week_month_all_and_by_type():
    es = [dict(date="2026-11-23", type="show", minutes=52),     # Monday of this week
          dict(date="2026-11-26", type="course", minutes=30),
          dict(date="2026-11-22", type="show", minutes=40),     # Sunday: last week, this month
          dict(date="2026-10-31", type="podcast", minutes=20)]  # last month
    t = lb.totals(es, TODAY)
    assert t["week"]["minutes"] == 82 and t["week"]["by_type"] == {"show": 52, "course": 30}
    assert t["month"]["minutes"] == 122
    assert t["all"]["minutes"] == 142 and t["all"]["by_type"]["podcast"] == 20
    assert t["week_from"] == "2026-11-23" and t["entries"] == 4
    assert lb.totals(es, TODAY, week_start=6)["week"]["minutes"] == 122    # weeks starting Sunday


def test_entry_checks():
    raises(lambda: lb.clean_entry(E(title="   "), TODAY), "title")
    raises(lambda: lb.clean_entry(E(kind="film"), TODAY), "type")
    raises(lambda: lb.clean_entry(E(link="javascript:alert(1)"), TODAY), "link")
    e = lb.clean_entry(E(title="  El   crimen  ", note=" good ", link="https://example.com/x"), TODAY)
    assert e["title"] == "El crimen" and e["note"] == "good" and e["link"] == "https://example.com/x"


def test_edit_and_delete():
    with tempfile.TemporaryDirectory() as d:
        s = settings(d)
        i = lb.add_entry(s, "es", E(), TODAY)["id"]
        lb.edit_entry(s, "es", i, E(minutes=35, title="Lesson 5 again"), TODAY)
        e = lb.load_log(d, "es")["entries"][0]
        assert (e["minutes"], e["title"], e["id"]) == (35, "Lesson 5 again", i)
        raises(lambda: lb.edit_entry(s, "es", i, E(minutes=0), TODAY), "between")
        raises(lambda: lb.edit_entry(s, "es", "nope", E(), TODAY), "no longer")
        lb.delete_entry(s, "es", i)
        assert lb.load_log(d, "es")["entries"] == []
        raises(lambda: lb.delete_entry(s, "es", i), "no longer")


def test_backups_keep_the_last_ten_and_hold_the_previous_version():
    with tempfile.TemporaryDirectory() as d:
        s = settings(d)
        for n in range(14):
            lb.add_entry(s, "es", E(title="Lesson %d" % n), TODAY)
        b = lb.backups(d, "es")
        assert len(b) == 10
        newest = json.load(open(b[-1], encoding="utf-8"))
        assert len(newest["entries"]) == 13 and len(lb.load_log(d, "es")["entries"]) == 14
        assert lb.backups(d, "fr") == []


def test_log_file_is_plain_readable_text():
    with tempfile.TemporaryDirectory() as d:
        lb.add_entry(settings(d), "es", E(title="Aquí no hay quien viva S01E01", kind="show", minutes=48), TODAY)
        text = open(lb.log_path(d, "es"), encoding="utf-8").read()
        assert "Aquí no hay quien viva S01E01" in text and '"minutes": 48' in text


def test_order_newest_first():
    es = [dict(date="2026-11-25", added="2026-11-25T09:00:00", title="a"),
          dict(date="2026-11-26", added="2026-11-26T08:00:00", title="b"),
          dict(date="2026-11-26", added="2026-11-26T20:00:00", title="c")]
    assert [e["title"] for e in lb.ordered(es)] == ["c", "b", "a"]


def test_folder_must_be_chosen_and_exist():
    raises(lambda: lb.add_entry(settings(""), "es", E(), TODAY), "choose a data folder")
    raises(lambda: lb.add_entry(settings("/no/such/folder/here"), "es", E(), TODAY), "can't be found")
    st = lb.state(settings(""), "es", TODAY)
    assert st["configured"] is False and st["error"] == ""


# ───────────── stage 2: fast entry and lookups ─────────────
def test_next_title():
    assert lb.next_title("Pimsleur Spanish L1 Lesson 5") == "Pimsleur Spanish L1 Lesson 6"
    assert lb.next_title("El crimen de Pazos S01E03") == "El crimen de Pazos S01E04"
    assert lb.next_title("Show S01E09") == "Show S01E10"
    assert lb.next_title("Lesson 099") == "Lesson 100"
    assert lb.next_title("Conversation with a tutor") is None
    assert lb.series_key("Pimsleur  Spanish L1 Lesson 5") == "pimsleur spanish l1 lesson"
    assert lb.series_key("2049") is None and lb.series_key("No number") is None


def test_examples_2_and_3_next_in_series_is_offered():
    with tempfile.TemporaryDirectory() as d:
        s = settings(d)
        lb.add_entry(s, "es", E(date="2026-11-25"), TODAY)
        lb.add_entry(s, "es", E(title="El crimen de Pazos S01E01", kind="show", minutes=52), TODAY)
        nxt = lb.state(s, "es", TODAY)["suggest"]["next"]
        assert {"title": "El crimen de Pazos S01E02", "type": "show", "minutes": 52,
                "after": "El crimen de Pazos S01E01"} == nxt[0]
        assert (nxt[1]["title"], nxt[1]["type"], nxt[1]["minutes"]) == ("Pimsleur Spanish L1 Lesson 6", "course", 30)


def test_suggestions_follow_the_newest_entry_and_skip_logged_ones():
    es = [dict(date="2026-11-20", added="a", title="Lesson 5", type="course", minutes=30),
          dict(date="2026-11-21", added="b", title="Lesson 6", type="course", minutes=28),
          dict(date="2026-11-10", added="c", title="Lesson 7", type="course", minutes=30),   # back-filled
          dict(date="2026-11-22", added="d", title="Tutor chat", type="conversation", minutes=45)]
    sg = lb.suggestions(es)
    assert [(n["title"], n["minutes"]) for n in sg["next"]] == [("Lesson 8", 28)]
    assert [t["title"] for t in sg["titles"]] == ["Tutor chat", "Lesson 6", "Lesson 5", "Lesson 7"]
    many = [dict(date="2026-11-%02d" % (n + 1), added="", title="Series%s 1" % chr(65 + n), type="show", minutes=10)
            for n in range(8)]
    assert len(lb.suggestions(many)["next"]) == 5
    assert lb.suggestions(many)["next"][0]["title"] == "SeriesH 2"            # most recent first
    assert lb.suggestions([]) == {"next": [], "titles": []}
    linked = [dict(date="2026-11-22", added="", title="Easy Spanish 301", type="other", minutes=13, link="https://youtu.be/x")]
    assert lb.suggestions(linked)["next"] == [] and lb.suggestions(linked)["titles"][0]["title"] == "Easy Spanish 301"
    same_second = [dict(date="2026-11-26", added="t", title="A 1", type="show", minutes=5),
                   dict(date="2026-11-26", added="t", title="B 1", type="show", minutes=5)]
    assert [n["title"] for n in lb.suggestions(same_second)["next"]] == ["B 2", "A 2"]   # the later one first


def test_youtube_links_are_recognised_and_nothing_else():
    ok = ["https://www.youtube.com/watch?v=abcdefghijk", "https://youtu.be/abcdefghijk?t=30",
          "https://m.youtube.com/watch?v=abcdefghijk&list=PL1", "http://youtube.com/shorts/abcdefghijk",
          "https://music.youtube.com/watch?v=abc-def_hij"]
    assert all(lb.youtube_id(u) for u in ok)
    assert lb.youtube_id(ok[1]) == "abcdefghijk"
    for bad in ["https://www.netflix.com/watch/80100172", "https://evil.example/watch?v=abcdefghijk",
                "https://youtube.com.evil.example/watch?v=abcdefghijk", "https://www.youtube.com/watch?v=short",
                "https://www.youtube.com/@channel", "file:///etc/passwd", "youtube.com/watch?v=abcdefghijk",
                "Pimsleur Lesson 5", ""]:
        assert lb.youtube_id(bad) is None, bad


YT_PAGE = ('<html><head><meta property="og:title" content="Espa&ntilde;ol con Juan &amp; amigos">'
           '</head><body><script>var x={"videoDetails":{"lengthSeconds":"1290"}};</script></body></html>')


def test_example_13_youtube_link_fills_title_and_duration():
    seen = []
    r = lb.lookup("https://youtu.be/abcdefghijk", settings("x"), get=lambda url, h=None: seen.append(url) or YT_PAGE)
    assert r == {"source": "YouTube", "title": "Español con Juan & amigos", "minutes": 22,
                 "link": "https://www.youtube.com/watch?v=abcdefghijk"}
    assert seen == ["https://www.youtube.com/watch?v=abcdefghijk"]             # only the rebuilt address is fetched
    assert lb.parse_youtube('<meta itemprop="duration" content="PT1H2M30S"><meta name="title" content="T">') == ("T", 3750)
    assert lb.parse_youtube("<html>consent page</html>") == (None, None)
    assert lb.minutes_of(20) == 1 and lb.minutes_of(89) == 1 and lb.minutes_of(90) == 2


def test_example_14_failed_lookup_gives_a_plain_message():
    def offline(url, h=None):
        raise ValueError(lb.LOOKUP_FAILED % "no connection")
    raises(lambda: lb.lookup("https://youtu.be/abcdefghijk", settings("x"), get=offline), "type the duration yourself")
    raises(lambda: lb.lookup("https://youtu.be/abcdefghijk", settings("x"), get=lambda u, h=None: "<html></html>"),
           "didn't give a length")
    off = dict(settings("x"), lookups=False)
    raises(lambda: lb.lookup("https://youtu.be/abcdefghijk", off, get=offline), "turned off")
    raises(lambda: lb.lookup("https://www.netflix.com/watch/80100172", settings("x"), get=offline), "can look up")


def test_episode_length_from_tmdb():
    calls = []

    def fake(url, headers=None):
        calls.append((url, headers))
        if "/search/tv" in url:
            return json.dumps({"results": [{"id": 4242, "name": "El crimen de Pazos"}, {"id": 1, "name": "Other"}]})
        if url.startswith(lb.TMDB + "/tv/4242/season/1/episode/2"):
            return json.dumps({"runtime": 52})
        if "/episode/3" in url:
            return json.dumps({"runtime": None})
        raise ValueError(lb.LOOKUP_FAILED % "the site answered 404")

    s = dict(settings("x"), tmdb_key="k" * 32)
    assert lb.lookup("El crimen de Pazos S01E02", s, get=fake) == {"source": "TMDB", "minutes": 52,
                                                                    "show": "El crimen de Pazos"}
    assert "query=El+crimen+de+Pazos" in calls[0][0] and "api_key=" + "k" * 32 in calls[0][0]
    assert lb.lookup("el crimen de pazos - s1e2", s, get=fake)["minutes"] == 52
    raises(lambda: lb.lookup("El crimen de Pazos S01E03", s, get=fake), "no running time")
    raises(lambda: lb.lookup("El crimen de Pazos S01E09", s, get=fake), "no S01E09")
    raises(lambda: lb.lookup("El crimen de Pazos S01E02", settings("x"), get=fake), "TMDB key")
    calls.clear()
    token = "t" * 200                                                         # a long key is sent as a header

    def fake_v4(url, headers=None):
        calls.append((url, headers))
        return json.dumps({"results": [{"id": 7, "name": "Show"}]} if "/search/tv" in url else {"runtime": 40})

    assert lb.lookup("Show S01E02", dict(s, tmdb_key=token), get=fake_v4)["minutes"] == 40
    assert all(h == {"Authorization": "Bearer " + token} and "api_key" not in u for u, h in calls)


def test_settings_keep_the_key_out_of_the_page():
    with tempfile.TemporaryDirectory() as d:
        os.environ["LOGBOOK_SETTINGS"] = os.path.join(d, "s.json")
        try:
            s = settings(d)
            lb.set_options(s, {"lookups": False, "tmdb_key": "a" * 32})
            saved = lb.load_settings()
            assert saved["lookups"] is False and saved["tmdb_key"] == "a" * 32
            st = lb.state(saved, "es", TODAY)
            assert st["tmdb"] is True and st["lookups"] is False and "a" * 32 not in json.dumps(st)
            raises(lambda: lb.set_options(s, {"tmdb_key": "has spaces and <tags>"}), "TMDB key")
            lb.set_options(s, {"lookups": True})
            assert lb.load_settings()["tmdb_key"] == "a" * 32                  # untouched when not sent
        finally:
            del os.environ["LOGBOOK_SETTINGS"]


def test_secure_lookups_fall_back_to_other_certificate_sets():
    import io, ssl, urllib.error
    tried = []

    class Page(io.BytesIO):
        def __enter__(self): return self
        def __exit__(self, *a): return False

    def first_fails(req, timeout=None, context=None):
        tried.append(context)
        if len(tried) == 1:
            raise urllib.error.URLError(ssl.SSLCertVerificationError("no local issuer certificate"))
        return Page(b"hello")

    lb.GOOD_CONTEXT.clear()
    if any(os.path.isfile(f) for f in lb.CA_FILES):
        assert lb.http_get("https://www.youtube.com/watch?v=abcdefghijk", opener=first_fails) == "hello"
        assert len(tried) == 2 and lb.GOOD_CONTEXT == [tried[1]]
        tried.clear()
        lb.http_get("https://www.youtube.com/watch?v=abcdefghijk", opener=lambda r, timeout=None, context=None: Page(b"x"))
    lb.GOOD_CONTEXT.clear()

    def never(req, timeout=None, context=None):
        raise urllib.error.URLError(ssl.SSLCertVerificationError("no local issuer certificate"))
    raises(lambda: lb.http_get("https://www.youtube.com/watch?v=abcdefghijk", opener=never), "Install Certificates")

    def down(req, timeout=None, context=None):
        raise urllib.error.URLError(OSError("nodename nor servname provided"))
    raises(lambda: lb.http_get("https://www.youtube.com/watch?v=abcdefghijk", opener=down), "no connection: ")


def test_episode_titles_in_other_spellings():
    for t in ["Show S01E02", "show s1e2", "Show - S01 E02", "Show 1x02", "El crimen de Pazos 1x2"]:
        m = lb.EPISODE.match(t)
        assert m and int(m.group(2) or m.group(4)) == 1 and int(m.group(3) or m.group(5)) == 2, t
    for t in ["Show", "Lesson 5", "S01E02", "1920x1080"]:
        assert not lb.EPISODE.match(t), t


# ───────────── stage 3: card numbers from Waypoint ─────────────
def stats_file(folder, days):
    with open(os.path.join(folder, lb.STATS_FILE), "w", encoding="utf-8") as f:
        json.dump({"app": "PathToFluent Waypoint", "format": 1, "days": days}, f)


def day(date, known, lang="es", **kw):
    return dict({"date": date, "language": lang, "known_words": known, "learning_words": 40,
                 "known_sentences": 100, "cards_studied": 480, "cards_ready": 25, "cards_waiting": 604}, **kw)


def test_example_6_no_stats_file_shows_time_only():
    with tempfile.TemporaryDirectory() as d:
        s = settings(d)
        lb.add_entry(s, "es", E(), TODAY)
        st = lb.state(s, "es", TODAY)
        assert st["cards"] == {"numbers": None, "note": ""} and st["totals"]["all"]["minutes"] == 30


def test_card_numbers_and_their_change():
    with tempfile.TemporaryDirectory() as d:
        stats_file(d, [day("2026-10-20", 200), day("2026-10-27", 240), day("2026-11-18", 290), day("2026-11-19", 300),
                       day("2026-11-25", 310), day("2026-11-26", 312), day("2026-11-26", 9, lang="fr"),
                       day("2026-11-27", 999)])                       # a line dated after today is ignored
        n = lb.state(settings(d), "es", TODAY)["cards"]["numbers"]
        assert n == {"date": "2026-11-26", "known_words": 312, "learning_words": 40, "cards_studied": 480,
                     "cards_waiting": 604, "change7": 12, "change30": 72}  # vs 19 Nov (300) and 27 Oct (240)
        assert lb.state(settings(d), "fr", TODAY)["cards"]["numbers"]["known_words"] == 9


def test_changes_are_left_out_when_the_file_has_no_old_days():
    with tempfile.TemporaryDirectory() as d:
        stats_file(d, [day("2026-11-25", 310), day("2026-11-26", 312)])
        n = lb.state(settings(d), "es", TODAY)["cards"]["numbers"]
        assert (n["known_words"], n["change7"], n["change30"]) == (312, None, None)
        stats_file(d, [day("2026-11-10", 280)])                       # not reconciled lately: still shown, with its date
        n = lb.state(settings(d), "es", TODAY)["cards"]["numbers"]
        assert (n["date"], n["known_words"], n["change7"]) == ("2026-11-10", 280, 0)
        stats_file(d, [])
        assert lb.state(settings(d), "es", TODAY)["cards"]["numbers"] is None


def test_damaged_stats_file_never_breaks_the_log():
    with tempfile.TemporaryDirectory() as d:
        s = settings(d)
        lb.add_entry(s, "es", E(), TODAY)
        for bad in ("{ not json", '{"days": 5}', '{"days": [{"date": "soon", "language": "es"}]}', "[]"):
            open(os.path.join(d, lb.STATS_FILE), "w").write(bad)
            st = lb.state(s, "es", TODAY)
            assert st["cards"]["numbers"] is None and "time only" in st["cards"]["note"], bad
            assert st["error"] == "" and st["totals"]["all"]["minutes"] == 30
        stats_file(d, [day("2026-11-26", "many")])                     # a number that isn't a number
        assert lb.state(s, "es", TODAY)["cards"]["numbers"]["known_words"] is None


def test_logbook_never_writes_the_stats_file_and_can_read_it_elsewhere():
    with tempfile.TemporaryDirectory() as d, tempfile.TemporaryDirectory() as other:
        stats_file(other, [day("2026-11-26", 312)])
        before = open(os.path.join(other, lb.STATS_FILE)).read()
        s = dict(settings(d), stats_folder=other)
        lb.add_entry(s, "es", E(), TODAY)
        assert lb.state(s, "es", TODAY)["cards"]["numbers"]["known_words"] == 312
        assert open(os.path.join(other, lb.STATS_FILE)).read() == before
        assert not os.path.exists(os.path.join(d, lb.STATS_FILE))
        os.environ["LOGBOOK_SETTINGS"] = os.path.join(d, "s.json")
        try:
            raises(lambda: lb.set_options(s, {"stats_folder": os.path.join(d, "nope")}), "doesn't exist")
            lb.set_options(s, {"stats_folder": ""})
            assert lb.load_settings()["stats_folder"] == ""
        finally:
            del os.environ["LOGBOOK_SETTINGS"]


def test_reads_the_file_waypoint_really_writes():
    way = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "waypoint", "addon")
    if not os.path.isfile(os.path.join(way, "daily.py")):
        return                                                         # Waypoint's source isn't next door
    sys.path.insert(0, way)
    import daily
    with tempfile.TemporaryDirectory() as d:
        stats = {"known_words": 300, "learning_words": 41, "known_sentences": 90, "ready": 20, "held": 610}
        daily.write(d, daily.day_line(stats, 470, "es", D(2026, 11, 19)))
        for known in (305, 312):                                       # example 7: several runs in one day
            daily.write(d, daily.day_line(dict(stats, known_words=known), 480, "es", TODAY))
        assert len(json.load(open(os.path.join(d, lb.STATS_FILE)))["days"]) == 2
        n = lb.state(settings(d), "es", TODAY)["cards"]["numbers"]
        assert (n["known_words"], n["cards_studied"], n["cards_waiting"], n["change7"]) == (312, 480, 610, 12)


# ───────────── stage 4: milestones and the summary file ─────────────
def test_milestone_steps():
    assert lb.steps_upto(9.9, lb.HOUR_STEPS) == [] and lb.steps_upto(10, lb.HOUR_STEPS) == [10]
    assert lb.steps_upto(320, lb.HOUR_STEPS) == [10, 25, 50, 100, 200, 300]
    assert lb.steps_upto(2100, lb.WORD_STEPS) == [100, 250, 500, 1000, 1500, 2000]
    assert [lb.next_step(v, lb.HOUR_STEPS) for v in (0, 10, 99.5, 100, 250)] == [10, 25, 100, 200, 300]
    assert [lb.next_step(v, lb.WORD_STEPS) for v in (312, 1000, 1499, 1500)] == [500, 1500, 1500, 2000]


def big(date, hours, title="Marathon"):
    return dict(title=title, type="show", minutes=int(hours * 60), date=date)


def test_examples_8_and_9_hundred_hours_recorded_once():
    with tempfile.TemporaryDirectory() as d:
        s = settings(d)
        for n in range(4):                                             # 96 hours on earlier days
            lb.add_entry(s, "es", big("2026-11-2%d" % n, 24, "Day %d" % n), TODAY)
        lb.add_entry(s, "es", big("2026-11-25", 3, "Evening"), TODAY)
        lb.add_entry(s, "es", dict(title="Almost", type="show", minutes=40, date="2026-11-25"), TODAY)   # 99 h 40
        ids = lambda: [m["id"] for m in lb.load_log(d, "es")["milestones"]]
        assert ids() == ["hours-10", "hours-25", "hours-50"]
        last = lb.add_entry(s, "es", dict(title="Over the line", type="show", minutes=30), TODAY)["id"]  # 100 h 10
        m = [x for x in lb.load_log(d, "es")["milestones"] if x["id"] == "hours-100"][0]
        assert (m["date"], m["label"], m["kind"], m["value"]) == ("2026-11-26", "100 hours of Spanish", "hours", 100)
        assert "hours-100" in [x["label"] and x["id"] for x in lb.state(s, "es", TODAY)["milestones"]]
        lb.delete_entry(s, "es", last, TODAY)                          # back under 100 hours
        assert lb.state(s, "es", TODAY)["totals"]["all"]["minutes"] == 99 * 60 + 40
        assert ids().count("hours-100") == 1
        lb.add_entry(s, "es", dict(title="Over again", type="show", minutes=60), D(2026, 11, 27))
        again = [x for x in lb.load_log(d, "es")["milestones"] if x["id"] == "hours-100"]
        assert len(again) == 1 and again[0]["date"] == "2026-11-26"    # not announced a second time


def test_milestones_are_dated_the_day_they_were_passed():
    with tempfile.TemporaryDirectory() as d:
        s = settings(d)
        lb.add_entry(s, "es", big("2026-11-03", 12), TODAY)            # back-filled
        lb.add_entry(s, "es", big("2026-11-01", 6, "Earlier"), TODAY)  # now 10 h was reached on the 3rd still
        m = {x["id"]: x["date"] for x in lb.load_log(d, "es")["milestones"]}
        assert m == {"hours-10": "2026-11-03"}


def test_known_word_milestones_come_from_the_stats_file():
    with tempfile.TemporaryDirectory() as d:
        s = settings(d)
        stats_file(d, [day("2026-11-10", 90), day("2026-11-15", 120), day("2026-11-26", 312), day("2026-11-26", 600, lang="fr")])
        st = lb.state(s, "es", TODAY)
        got = {m["id"]: (m["date"], m["label"]) for m in st["milestones"]}
        assert got == {"words-100": ("2026-11-15", "100 known words"), "words-250": ("2026-11-26", "250 known words")}
        assert st["progress"]["words_next"] == 500 and st["progress"]["words_to_go"] == 188
        assert st["progress"]["hours_next"] == 10 and st["progress"]["minutes_to_go"] == 600
        stats_file(d, [day("2026-11-26", 80)])                         # numbers drop: nothing is taken back
        assert len(lb.state(s, "es", TODAY)["milestones"]) == 2
        assert len(lb.backups(d, "es")) == 0                           # and nothing was re-saved for no reason


def test_finishing_a_show_is_a_milestone_i_record_and_can_take_back():
    with tempfile.TemporaryDirectory() as d:
        s = settings(d)
        lb.add_entry(s, "es", E(title="El crimen de Pazos S01E06", kind="show", minutes=50), TODAY)
        lb.add_entry(s, "es", E(), TODAY)
        lb.add_entry(s, "es", E(title="Easy Spanish podcast 12", kind="podcast"), TODAY)
        lb.add_entry(s, "es", E(title="Ocho apellidos vascos", kind="show", minutes=98), TODAY)
        cands = lb.state(s, "es", TODAY)["finishable"]
        assert cands == [{"title": "Ocho apellidos vascos", "type": "show"}, {"title": "Pimsleur Spanish L1", "type": "course"},
                         {"title": "El crimen de Pazos", "type": "show"}]
        lb.finish(s, "es", {"title": "El crimen de Pazos", "type": "show"}, TODAY)
        st = lb.state(s, "es", TODAY)
        m = st["milestones"][0]
        assert (m["label"], m["kind"], m["date"]) == ("Finished El crimen de Pazos", "finished", "2026-11-26")
        assert "El crimen de Pazos" not in [c["title"] for c in st["finishable"]]
        raises(lambda: lb.finish(s, "es", {"title": "el crimen de pazos"}, TODAY), "already")
        raises(lambda: lb.finish(s, "es", {"title": ""}, TODAY), "what you finished")
        raises(lambda: lb.finish(s, "es", {"title": "X", "date": "2026-12-01"}, TODAY), "future")
        lb.unfinish(s, "es", m["id"], TODAY)
        assert lb.state(s, "es", TODAY)["milestones"] == []
        lb.add_entry(s, "es", big("2026-11-20", 11), TODAY)
        raises(lambda: lb.unfinish(s, "es", "hours-10", TODAY), "can't be removed")


def test_summary_file_has_the_numbers_and_only_what_i_typed():
    with tempfile.TemporaryDirectory() as d:
        s = settings(d)
        stats_file(d, [day("2026-11-19", 300), day("2026-11-26", 312)])
        lb.add_entry(s, "es", E(title="Last week show S01E01", kind="show", minutes=50, date="2026-11-18"), TODAY)
        lb.add_entry(s, "es", E(date="2026-11-23", note="felt easy", link="https://example.com/private"), TODAY)
        lb.add_entry(s, "es", big("2026-11-24", 10.5, "Long weekend binge"), TODAY)
        text = open(lb.summary_path(d, "es"), encoding="utf-8").read()
        sm = json.loads(text)
        assert sm["language"] == "es" and sm["language_name"] == "Spanish" and sm["date"] == "2026-11-26"
        assert sm["this_week"]["from"] == "2026-11-23" and sm["this_week"]["to"] == "2026-11-29"
        assert sm["this_week"]["minutes"] == 660 and sm["this_week"]["hours"] == 11.0
        assert sm["this_week"]["by_type"] == {"course": 30, "show": 630}
        assert [e["title"] for e in sm["this_week"]["entries"]] == ["Pimsleur Spanish L1 Lesson 5", "Long weekend binge"]
        assert sm["this_week"]["entries"][0]["note"] == "felt easy"
        assert [e["title"] for e in sm["last_week"]["entries"]] == ["Last week show S01E01"] and sm["last_week"]["minutes"] == 50
        assert sm["all_time"] == {"minutes": 710, "hours": 11.8, "by_type": {"show": 680, "course": 30}, "entries": 3,
                                  "first_day": "2026-11-18"}
        assert sm["cards"]["known_words"] == 312 and sm["cards"]["change7"] == 12
        assert [m["label"] for m in sm["milestones_new"]] == ["100 known words", "250 known words", "10 hours of Spanish"]
        assert sm["next"]["hours_next"] == 25 and sm["summary_last_used"] is None
        assert d not in text and "example.com" not in text and "recorded" not in text and '"id"' not in text


def test_new_milestones_are_the_ones_since_the_summary_was_last_used():
    with tempfile.TemporaryDirectory() as d:
        s = settings(d)
        lb.add_entry(s, "es", big("2026-11-20", 11), TODAY)
        read = lambda: json.load(open(lb.summary_path(d, "es"), encoding="utf-8"))
        assert [m["label"] for m in read()["milestones_new"]] == ["10 hours of Spanish"]
        stamp = lb.mark_used(d, "es", now=datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=2))
        assert abs((datetime.datetime.fromisoformat(stamp) - datetime.datetime.utcnow()).total_seconds()) < 60   # UTC
        lb.state(s, "es", TODAY)
        sm = read()
        assert sm["milestones_new"] == [] and sm["summary_last_used"] == stamp
        assert [m["label"] for m in sm["milestones_all"]] == ["10 hours of Spanish"]
        log = lb.load_log(d, "es")                                     # a later milestone is new again
        log["milestones"].append({"id": "finished-x", "kind": "finished", "type": "show", "title": "X", "date": "2026-11-26",
                                  "label": "Finished X", "recorded": "2099-01-01T00:00:00"})
        lb.save_log(d, "es", log)
        lb.state(s, "es", TODAY)
        assert [m["label"] for m in read()["milestones_new"]] == ["Finished X"]
        open(lb.used_path(d, "es"), "w").write("garbage")              # a bad marker counts as never used
        assert lb.last_used(d, "es") == ""


def test_summary_is_not_rewritten_when_nothing_changed():
    with tempfile.TemporaryDirectory() as d:
        s = settings(d)
        lb.add_entry(s, "es", E(), TODAY)
        p = lb.summary_path(d, "es")
        os.utime(p, (1, 1))
        lb.state(s, "es", TODAY)
        assert os.path.getmtime(p) == 1
        lb.state(s, "es", D(2026, 11, 27))                             # a new day changes it
        assert os.path.getmtime(p) != 1


def test_command_line_summary_and_mark_used():
    import subprocess
    here = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "logbook.py")
    with tempfile.TemporaryDirectory() as d, tempfile.TemporaryDirectory() as home:
        env = dict(os.environ, LOGBOOK_SETTINGS=os.path.join(home, "none.json"))
        run = lambda *a: subprocess.run([sys.executable, here] + list(a), capture_output=True, text=True, env=env)
        r = run("--summary", "--folder", d)
        assert r.returncode == 1 and "No log found" in r.stdout
        lb.add_entry(settings(d), "es", E(), datetime.date.today())
        os.remove(lb.summary_path(d, "es"))
        r = run("--summary", "--folder", d)
        assert r.returncode == 0 and "es: 30 min this week, 30 min in all" in r.stdout, r.stdout + r.stderr
        assert os.path.exists(lb.summary_path(d, "es"))
        r = run("--mark-used", "--folder", d, "--lang", "es")
        assert r.returncode == 0 and "marked as used" in r.stdout and lb.last_used(d, "es")
        r = run("--summary", "--folder", os.path.join(d, "missing"))
        assert r.returncode != 0 and "can't be found" in r.stderr
        open(lb.log_path(d, "es"), "w").write("{ broken")
        r = run("--summary", "--folder", d)
        assert r.returncode != 0 and "can't be read" in r.stderr and open(lb.log_path(d, "es")).read() == "{ broken"


if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    failed = 0
    for name, fn in tests:
        try:
            fn()
        except Exception as e:
            failed += 1
            print("FAIL %s: %r" % (name, e))
    print("%d passed, %d failed" % (len(tests) - failed, failed))
    sys.exit(1 if failed else 0)
