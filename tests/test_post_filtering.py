from wp_log_parser.wordpress import sort_and_limit_posts


def test_sort_and_limit_posts_ascending_order():
    """Verify posts are sorted by date in ascending order (earliest → latest)."""
    posts = [
        {"id": 3, "date": "2026-01-03", "title": "C", "status": "publish"},
        {"id": 1, "date": "2026-01-01", "title": "A", "status": "publish"},
        {"id": 2, "date": "2026-01-02", "title": "B", "status": "publish"},
    ]
    result = sort_and_limit_posts(posts)
    assert len(result) == 3
    assert result[0]["id"] == 1
    assert result[1]["id"] == 2
    assert result[2]["id"] == 3
    assert result[0]["date"] == "2026-01-01"
    assert result[2]["date"] == "2026-01-03"


def test_sort_and_limit_posts_keep_all_when_no_limit():
    """When limit is None, keep all posts sorted ascending."""
    posts = [
        {"id": 2, "date": "2026-01-02", "title": "B", "status": "publish"},
        {"id": 1, "date": "2026-01-01", "title": "A", "status": "publish"},
    ]
    result = sort_and_limit_posts(posts, limit=None)
    assert len(result) == 2
    assert result[0]["id"] == 1
    assert result[1]["id"] == 2


def test_sort_and_limit_posts_latest_posts_with_limit():
    """When limit is specified, return only the most recent N posts in ascending order."""
    posts = [
        {"id": 1, "date": "2026-01-01", "title": "A", "status": "publish"},
        {"id": 2, "date": "2026-01-02", "title": "B", "status": "publish"},
        {"id": 3, "date": "2026-01-03", "title": "C", "status": "publish"},
        {"id": 4, "date": "2026-01-04", "title": "D", "status": "publish"},
        {"id": 5, "date": "2026-01-05", "title": "E", "status": "publish"},
    ]
    result = sort_and_limit_posts(posts, limit=2)
    assert len(result) == 2
    assert result[0]["id"] == 4  # Second-to-last post
    assert result[1]["id"] == 5  # Last post (most recent)
    assert result[0]["date"] == "2026-01-04"
    assert result[1]["date"] == "2026-01-05"


def test_sort_and_limit_posts_limit_larger_than_list():
    """When limit is larger than the list size, return all posts sorted ascending."""
    posts = [
        {"id": 2, "date": "2026-01-02", "title": "B", "status": "publish"},
        {"id": 1, "date": "2026-01-01", "title": "A", "status": "publish"},
    ]
    result = sort_and_limit_posts(posts, limit=10)
    assert len(result) == 2
    assert result[0]["id"] == 1
    assert result[1]["id"] == 2


def test_sort_and_limit_posts_latest_is_last_element():
    """The last element of the returned list must always be the latest post."""
    posts = [
        {"id": 5, "date": "2026-01-05", "title": "E", "status": "publish"},
        {"id": 2, "date": "2026-01-02", "title": "B", "status": "publish"},
        {"id": 4, "date": "2026-01-04", "title": "D", "status": "publish"},
        {"id": 1, "date": "2026-01-01", "title": "A", "status": "publish"},
        {"id": 3, "date": "2026-01-03", "title": "C", "status": "publish"},
    ]
    result = sort_and_limit_posts(posts, limit=3)
    assert result[-1]["date"] == "2026-01-05"  # Latest post is last
    assert result[-1]["id"] == 5


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
