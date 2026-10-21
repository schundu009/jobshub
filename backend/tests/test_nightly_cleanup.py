"""The Data tab's Cleanup runs nightly (celery_app.py nightly-jobs-cleanup)."""
from unittest.mock import MagicMock, patch


def test_nightly_cleanup_is_scheduled_with_a_long_limit():
    from celery_app import celery_app
    entry = celery_app.conf.beat_schedule["nightly-jobs-cleanup"]
    assert entry["task"] == "tasks.maintenance_tasks.nightly_jobs_cleanup"
    assert entry["schedule"].hour == {9} and entry["schedule"].minute == {30}
    assert celery_app.conf.task_annotations[entry["task"]]["time_limit"] >= 1800


def test_nightly_cleanup_deletes_old_jobs_then_duplicates_keeping_open_postings():
    from tasks import maintenance_tasks
    db = MagicMock()
    calls = []
    with patch.object(maintenance_tasks, "get_db", return_value=db), \
         patch("services.job_cleanup.old_jobs", side_effect=lambda *a, **k: calls.append(("old", a, k)) or {"deleted": 5}), \
         patch("services.job_cleanup.duplicates", side_effect=lambda *a, **k: calls.append(("dupes", a, k)) or {"deleted": 2}), \
         patch("services.redis_service.redis_service.cache_delete_pattern") as clear:
        result = maintenance_tasks.nightly_jobs_cleanup()
    assert result["status"] == "success"
    assert [c[0] for c in calls] == ["old", "dupes"]
    assert calls[0][1][1] == 7 and calls[0][2] == {"include_open": False, "apply": True}
    assert calls[1][2] == {"apply": True}
    clear.assert_called_once_with("analytics:*")
    db.close.assert_called_once()
