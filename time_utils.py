"""Time utilities for handling America/New_York timezone."""

from datetime import datetime, timedelta
from typing import List, Tuple
import pytz

from config import Config


# Timezone
ET_TZ = (
    pytz.FixedOffset(-300)
    if Config.USE_FIXED_UTC_MINUS_5
    else pytz.timezone("America/New_York")
)


def now_et() -> datetime:
    """Get current time in Eastern Time (America/New_York).

    Returns:
        Current datetime in ET timezone.
    """
    return datetime.now(tz=ET_TZ)


def format_dt(dt: datetime) -> str:
    """Format datetime to YYYY/MM/DD HH:MM:SS.

    Args:
        dt: Datetime object to format.

    Returns:
        Formatted string.
    """
    return dt.strftime(Config.DATE_FORMAT)


def parse_dt(dt_str: str) -> datetime:
    """Parse datetime string from YYYY/MM/DD HH:MM:SS format.

    Args:
        dt_str: Datetime string to parse.

    Returns:
        Datetime object in ET timezone.
    """
    dt = datetime.strptime(dt_str, Config.DATE_FORMAT)
    return ET_TZ.localize(dt) if dt.tzinfo is None else dt


def hour_from_label(label: str) -> int:
    """Convert time label (e.g., '9 AM') to 24-hour format.

    Args:
        label: Time label like '12 AM', '1 PM', etc.

    Returns:
        Hour in 24-hour format (0-23).
    """
    parts = label.split()
    h = int(parts[0])
    ampm = parts[1].upper()

    if ampm == "AM":
        return 0 if h == 12 else h
    else:
        return 12 if h == 12 else h + 12


def generate_am_times() -> List[str]:
    """Generate AM time labels (12 AM - 11 AM).

    Returns:
        List of time labels.
    """
    return [f"{h if h else 12} AM" for h in range(0, 12)]


def generate_pm_times() -> List[str]:
    """Generate PM time labels (12 PM - 11 PM).

    Returns:
        List of time labels.
    """
    return [f"{12 if h == 12 else h - 12} PM" for h in range(12, 24)]


def create_datetime_from_date_and_hour(date, hour: int) -> datetime:
    """Create datetime object from date and hour.

    Args:
        date: Date object.
        hour: Hour in 24-hour format (0-23).

    Returns:
        Datetime object in ET timezone.
    """
    dt = datetime(date.year, date.month, date.day, hour, 0, 0)
    return ET_TZ.localize(dt)


def get_server_date(offset_days: int = 0) -> Tuple[datetime, str]:
    """Get server date with optional offset.

    Args:
        offset_days: Number of days to offset (-1, 0, etc.).

    Returns:
        Tuple of (date object, formatted string).
    """
    dt = now_et() + timedelta(days=offset_days)
    return dt.date(), dt.strftime("%Y/%m/%d")
