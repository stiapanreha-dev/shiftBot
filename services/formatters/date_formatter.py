"""Date formatter - single source of truth for date format conversions.

This module centralizes all date format conversions to eliminate
scattered replace("/", "-") calls and ensure consistent formatting.

Formats:
- DISPLAY: YYYY/MM/DD HH:MM:SS (for user-facing messages)
- DB: YYYY-MM-DD (for PostgreSQL date columns)
- DB_DATETIME: YYYY-MM-DD HH:MM:SS (for PostgreSQL timestamp columns)
"""

from datetime import datetime, date
from typing import Union, Optional


class DateFormatter:
    """Single source of truth for date format conversions."""

    # Format constants
    DISPLAY_FORMAT = "%Y/%m/%d %H:%M:%S"
    DISPLAY_DATE_FORMAT = "%Y/%m/%d"
    DB_DATE_FORMAT = "%Y-%m-%d"
    DB_DATETIME_FORMAT = "%Y-%m-%d %H:%M:%S"

    @staticmethod
    def to_db_date(value: Union[str, datetime, date]) -> str:
        """Convert any date format to PostgreSQL date format (YYYY-MM-DD).

        Args:
            value: Date as string (YYYY/MM/DD or YYYY-MM-DD), datetime, or date

        Returns:
            String in YYYY-MM-DD format

        Examples:
            >>> DateFormatter.to_db_date("2025/01/15")
            '2025-01-15'
            >>> DateFormatter.to_db_date(datetime(2025, 1, 15, 10, 30))
            '2025-01-15'
        """
        if isinstance(value, datetime):
            return value.strftime(DateFormatter.DB_DATE_FORMAT)
        elif isinstance(value, date):
            return value.strftime(DateFormatter.DB_DATE_FORMAT)
        elif isinstance(value, str):
            # Normalize string format
            return value.replace("/", "-").split()[0]  # Take date part only
        else:
            raise ValueError(f"Cannot convert {type(value)} to DB date format")

    @staticmethod
    def to_db_datetime(value: Union[str, datetime]) -> str:
        """Convert any datetime format to PostgreSQL timestamp format.

        Args:
            value: Datetime as string (YYYY/MM/DD HH:MM:SS) or datetime object

        Returns:
            String in YYYY-MM-DD HH:MM:SS format

        Examples:
            >>> DateFormatter.to_db_datetime("2025/01/15 10:30:00")
            '2025-01-15 10:30:00'
        """
        if isinstance(value, datetime):
            return value.strftime(DateFormatter.DB_DATETIME_FORMAT)
        elif isinstance(value, str):
            return value.replace("/", "-")
        else:
            raise ValueError(f"Cannot convert {type(value)} to DB datetime format")

    @staticmethod
    def to_display_date(value: Union[str, datetime, date]) -> str:
        """Convert any date format to display format (YYYY/MM/DD).

        Args:
            value: Date in any supported format

        Returns:
            String in YYYY/MM/DD format
        """
        if isinstance(value, datetime):
            return value.strftime(DateFormatter.DISPLAY_DATE_FORMAT)
        elif isinstance(value, date):
            return value.strftime(DateFormatter.DISPLAY_DATE_FORMAT)
        elif isinstance(value, str):
            return value.replace("-", "/").split()[0]
        else:
            raise ValueError(f"Cannot convert {type(value)} to display date format")

    @staticmethod
    def to_display_datetime(value: Union[str, datetime]) -> str:
        """Convert any datetime format to display format (YYYY/MM/DD HH:MM:SS).

        Args:
            value: Datetime in any supported format

        Returns:
            String in YYYY/MM/DD HH:MM:SS format
        """
        if isinstance(value, datetime):
            return value.strftime(DateFormatter.DISPLAY_FORMAT)
        elif isinstance(value, str):
            return value.replace("-", "/")
        else:
            raise ValueError(f"Cannot convert {type(value)} to display datetime format")

    @staticmethod
    def parse_date(value: str) -> date:
        """Parse date string to date object.

        Accepts both YYYY/MM/DD and YYYY-MM-DD formats.

        Args:
            value: Date string

        Returns:
            date object
        """
        normalized = value.replace("/", "-").split()[0]
        return datetime.strptime(normalized, DateFormatter.DB_DATE_FORMAT).date()

    @staticmethod
    def parse_datetime(value: str) -> datetime:
        """Parse datetime string to datetime object.

        Accepts both YYYY/MM/DD and YYYY-MM-DD formats.

        Args:
            value: Datetime string

        Returns:
            datetime object (naive, no timezone)
        """
        normalized = value.replace("/", "-")
        try:
            return datetime.strptime(normalized, DateFormatter.DB_DATETIME_FORMAT)
        except ValueError:
            # Try date-only format and add midnight time
            return datetime.strptime(normalized.split()[0], DateFormatter.DB_DATE_FORMAT)

    @staticmethod
    def extract_date_part(datetime_str: str) -> str:
        """Extract date part from datetime string.

        Args:
            datetime_str: String like "2025/01/15 10:30:00"

        Returns:
            Date part only "2025/01/15" or "2025-01-15"
        """
        return datetime_str.split()[0] if datetime_str else ""

    @staticmethod
    def normalize_to_db(value: Optional[str]) -> Optional[str]:
        """Normalize date string to DB format, handling None.

        This is a convenience method for the common pattern of
        normalizing optional date strings.

        Args:
            value: Date string or None

        Returns:
            Normalized string or None
        """
        if value is None:
            return None
        return value.replace("/", "-")
