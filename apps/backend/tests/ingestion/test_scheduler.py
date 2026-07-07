"""Scheduler unit tests."""
from hali.scheduler import setup_scheduler


def test_scheduler_registers_jobs():
    sched = setup_scheduler()
    job_ids = [job.id for job in sched.get_jobs()]
    assert "gdacs-daily" in job_ids


def test_scheduler_registers_ai_backlog_job_when_ai_enabled(monkeypatch):
    from hali.config import settings

    monkeypatch.setattr(settings, "gemini_api_key", "test-key")
    sched = setup_scheduler()
    job_ids = [job.id for job in sched.get_jobs()]
    assert "ai-backlog-daily" in job_ids
