from datetime import datetime, timezone

from upright.services import timesync


def test_clock_ok_true_for_now():
    assert timesync.clock_ok() is True


def test_status_shape():
    s = timesync.status()
    assert set(s) == {"clock_ok", "utc", "chrony"}
    assert isinstance(s["chrony"], bool)


def test_sync_now_safe_without_chrony(monkeypatch):
    # No chronyc / helper on a dev box — must not raise, and the (correct) host
    # clock means it still reports ok.
    monkeypatch.setattr(timesync.shutil, "which", lambda _name: None)
    assert timesync.sync_now() is True


def test_http_time_parses_date_header(monkeypatch):
    class _Resp:
        headers = {"Date": "Wed, 21 Jun 2026 12:00:00 GMT"}

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(timesync.urllib.request, "urlopen", lambda *a, **k: _Resp())
    when = timesync._http_time()
    assert when is not None
    assert when.astimezone(timezone.utc) == datetime(2026, 6, 21, 12, 0, tzinfo=timezone.utc)


def test_set_helper_skipped_when_absent(monkeypatch):
    monkeypatch.setattr(timesync.os.path, "exists", lambda _p: False)
    assert timesync._set_via_helper(datetime(2026, 6, 21, tzinfo=timezone.utc)) is False


def test_start_thread_noop_off_pi():
    th = timesync.start_thread(dry_run=True)
    assert th.is_alive()
    th.stop.set()
