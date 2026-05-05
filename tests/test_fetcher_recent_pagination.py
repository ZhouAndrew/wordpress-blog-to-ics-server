from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from wp_log_parser.config import AppConfig
from wp_log_parser.fetcher import list_recent_post_ids


def _post(post_id: int, dt: datetime) -> dict[str, str | int]:
    return {
        "id": post_id,
        "title": f"Post {post_id}",
        "date": dt.strftime("%Y-%m-%d %H:%M:%S"),
        "status": "publish",
        "modified_gmt": "",
    }


def test_list_recent_post_ids_paginates_beyond_first_100_and_stops_at_cutoff(monkeypatch):
    config = AppConfig(wordpress_mode="rest", timezone="UTC")
    now = datetime.now().replace(microsecond=0)

    recent_rows = [_post(1000 - i, now - timedelta(hours=i)) for i in range(120)]
    old_rows = [_post(2000 - i, now - timedelta(days=5, hours=i)) for i in range(10)]

    pages: dict[int, list[dict[str, str | int]]] = {
        1: recent_rows[:100],
        2: recent_rows[100:] + old_rows,
        3: [],
    }

    def fake_list_posts_rest(_base_url, _username, _app_password, _verify_ssl, per_page, limit, page):
        assert per_page == 100
        assert limit is None
        return pages.get(page, [])

    monkeypatch.setattr("wp_log_parser.fetcher.list_posts_rest", fake_list_posts_rest)

    ids = list_recent_post_ids(config, days=2)

    cutoff = datetime.now(ZoneInfo("UTC")) - timedelta(days=2)
    expected = [
        int(row["id"])
        for row in recent_rows
        if datetime.fromisoformat(str(row["date"])).replace(tzinfo=ZoneInfo("UTC")) >= cutoff
    ]
    assert ids == expected
