"""Scheduler unit tests."""
from hali.scheduler import setup_scheduler


def test_scheduler_registers_jobs():
    sched = setup_scheduler()
    job_ids = [job.id for job in sched.get_jobs()]
    assert "gdacs-daily" in job_ids
