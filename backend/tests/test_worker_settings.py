"""Regression guard: the debounced segmentation trigger must not be swallowed by arq."""

from backend.worker import WorkerSettings


def test_segmentation_job_keeps_no_result():
    # A stored result blocks re-enqueueing the same job id for keep_result
    # seconds (an hour by default), silencing the debounced trigger.
    fn = next(f for f in WorkerSettings.functions if getattr(f, "name", "") == "run_segmentation_job")
    assert fn.keep_result_s == 0
