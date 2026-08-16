import calendar
import threading
import time
from datetime import datetime

from app.services.report_service import ReportService


def start_monthly_report_scheduler(report_service: ReportService) -> threading.Event:
    stop_event = threading.Event()
    thread = threading.Thread(
        target=_run_scheduler,
        args=(report_service, stop_event),
        daemon=True,
        name="monthly-report-scheduler",
    )
    thread.start()
    return stop_event


def _run_scheduler(report_service: ReportService, stop_event: threading.Event) -> None:
    last_generated_key = ""
    while not stop_event.is_set():
        now = datetime.now()
        target = _month_end_target(now)
        if now >= target:
            key = f"{now.year}-{now.month:02d}"
            if key != last_generated_key:
                report_service.write_current_month_report()
                last_generated_key = key
            sleep_seconds = 60
        else:
            sleep_seconds = min((target - now).total_seconds(), 3600)
        stop_event.wait(max(sleep_seconds, 1))


def _month_end_target(now: datetime) -> datetime:
    last_day = calendar.monthrange(now.year, now.month)[1]
    return now.replace(day=last_day, hour=23, minute=59, second=0, microsecond=0)
