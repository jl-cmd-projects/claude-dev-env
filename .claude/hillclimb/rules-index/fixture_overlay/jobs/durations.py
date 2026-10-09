"""Format how long a job ran."""

from jobs.config.time_units import MINUTES_PER_HOUR, SECONDS_PER_MINUTE


def format_duration(total_seconds: int) -> str:
    """Return a duration as hours and minutes, like ``2h 05m``.

    Args:
        total_seconds: How long the job ran, in seconds.

    Returns:
        The hours and the zero-padded minutes.
    """
    hours, minutes = divmod(total_seconds // SECONDS_PER_MINUTE, MINUTES_PER_HOUR)
    return f"{hours}h {minutes:02d}m"
