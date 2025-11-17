from datetime import datetime, timedelta, timezone

from src.core.utils import time as time_utils


def test_now_utc_returns_timezone_aware():
    current = time_utils.now_utc()
    assert current.tzinfo == timezone.utc


def test_to_utc_converts_naive_and_aware():
    naive = datetime(2024, 1, 1, 12, 0, 0)
    converted = time_utils.to_utc(naive)
    assert converted.tzinfo == timezone.utc
    assert converted.hour == 12

    aware = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone(timedelta(hours=5)))
    converted_aware = time_utils.to_utc(aware)
    assert converted_aware.tzinfo == timezone.utc
    assert converted_aware.hour == 7  # 5 hours subtracted


def test_iso_utc_uses_passed_datetime():
    dt = datetime(2024, 3, 10, 8, 15, 0, tzinfo=timezone.utc)
    formatted = time_utils.iso_utc(dt)
    assert formatted.startswith("2024-03-10T08:15:00")
    assert formatted.endswith("+00:00")


def test_now_db_utc_returns_naive_datetime():
    db_time = time_utils.now_db_utc()
    assert db_time.tzinfo is None
