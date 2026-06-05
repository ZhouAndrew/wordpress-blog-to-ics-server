from wp_log_parser.wordpress import sort_and_limit_posts


def test_sort_and_limit_posts_ascending_order():
    """Verify posts are sorted by date in descending order (latest → earliest)."""
    posts = [
        {"id": 3, "date": "2026-01-03", "title": "C", "status": "publish"},
        {"id": 1, "date": "2026-01-01", "title": "A", "status": "publish"},
        {"id": 2, "date": "2026-01-02", "title": "B", "status": "publish"},
    ]
    result = sort_and_limit_posts(posts)
    assert len(result) == 3
    assert result[0]["id"] == 3
    assert result[1]["id"] == 2
    assert result[2]["id"] == 1
    assert result[0]["date"] == "2026-01-03"
    assert result[2]["date"] == "2026-01-01"


def test_sort_and_limit_posts_keep_all_when_no_limit():
    """When limit is None, keep all posts sorted newest-first."""
    posts = [
        {"id": 2, "date": "2026-01-02", "title": "B", "status": "publish"},
        {"id": 1, "date": "2026-01-01", "title": "A", "status": "publish"},
    ]
    result = sort_and_limit_posts(posts, limit=None)
    assert len(result) == 2
    assert result[0]["id"] == 2
    assert result[1]["id"] == 1


def test_sort_and_limit_posts_latest_posts_with_limit():
    """When limit is specified, return only the most recent N posts in newest-first order."""
    posts = [
        {"id": 1, "date": "2026-01-01", "title": "A", "status": "publish"},
        {"id": 2, "date": "2026-01-02", "title": "B", "status": "publish"},
        {"id": 3, "date": "2026-01-03", "title": "C", "status": "publish"},
        {"id": 4, "date": "2026-01-04", "title": "D", "status": "publish"},
        {"id": 5, "date": "2026-01-05", "title": "E", "status": "publish"},
    ]
    result = sort_and_limit_posts(posts, limit=2)
    assert len(result) == 2
    assert result[0]["id"] == 5  # Latest post
    assert result[1]["id"] == 4  # Next latest post
    assert result[0]["date"] == "2026-01-05"
    assert result[1]["date"] == "2026-01-04"


def test_sort_and_limit_posts_limit_larger_than_list():
    """When limit is larger than the list size, return all posts newest-first."""
    posts = [
        {"id": 2, "date": "2026-01-02", "title": "B", "status": "publish"},
        {"id": 1, "date": "2026-01-01", "title": "A", "status": "publish"},
    ]
    result = sort_and_limit_posts(posts, limit=10)
    assert len(result) == 2
    assert result[0]["id"] == 2
    assert result[1]["id"] == 1


def test_sort_and_limit_posts_latest_is_first_element():
    """The first element of the returned list must always be the latest post."""
    posts = [
        {"id": 5, "date": "2026-01-05", "title": "E", "status": "publish"},
        {"id": 2, "date": "2026-01-02", "title": "B", "status": "publish"},
        {"id": 4, "date": "2026-01-04", "title": "D", "status": "publish"},
        {"id": 1, "date": "2026-01-01", "title": "A", "status": "publish"},
        {"id": 3, "date": "2026-01-03", "title": "C", "status": "publish"},
    ]
    result = sort_and_limit_posts(posts, limit=3)
    assert result[0]["date"] == "2026-01-05"  # Latest post is first
    assert result[0]["id"] == 5


def test_sort_and_limit_posts_empty_list():
    """Sorting an empty list returns an empty list."""
    result = sort_and_limit_posts([], limit=5)
    assert result == []


def test_sort_and_limit_posts_single_post():
    """Limiting to a single post works correctly."""
    posts = [
        {"id": 2, "date": "2026-01-02", "title": "B", "status": "publish"},
        {"id": 1, "date": "2026-01-01", "title": "A", "status": "publish"},
    ]
    result = sort_and_limit_posts(posts, limit=1)
    assert len(result) == 1
    assert result[0]["id"] == 2  # Only the latest


def test_sort_and_limit_posts_mixed_date_formats_newest_first():
    posts = [
        {"id": 20, "date": "2026-01-07", "title": "plain-date", "status": "publish"},
        {"id": 30, "date": "2026-01-07T05:30:00Z", "title": "iso-z", "status": "publish"},
        {"id": 40, "date": "2026-01-06T23:30:00-06:00", "title": "iso-offset", "status": "publish"},
        {"id": 10, "date": "2026-01-07 06:00:00", "title": "space-seconds", "status": "publish"},
    ]

    result = sort_and_limit_posts(posts)

    assert [post["id"] for post in result] == [10, 40, 30, 20]


def test_sort_and_limit_posts_invalid_or_missing_dates_fall_back_and_tie_break_on_id():
    posts = [
        {"id": 2, "date": "", "title": "missing", "status": "publish"},
        {"id": 1, "date": "not-a-date", "title": "invalid", "status": "publish"},
        {"id": 3, "date": "2026-01-01", "title": "valid", "status": "publish"},
        {"id": 4, "title": "missing-key", "status": "publish"},
    ]

    result = sort_and_limit_posts(posts)

    assert [post["id"] for post in result] == [3, 4, 2, 1]


def test_sort_and_limit_posts_identical_dates_tie_break_on_numeric_id_descending():
    posts = [
        {"id": 10, "date": "2026-01-07 09:00:00", "title": "A", "status": "publish"},
        {"id": 12, "date": "2026-01-07 09:00:00", "title": "B", "status": "publish"},
        {"id": 11, "date": "2026-01-07 09:00:00", "title": "C", "status": "publish"},
    ]

    result = sort_and_limit_posts(posts)

    assert [post["id"] for post in result] == [12, 11, 10]
