"""Format how long a job ran."""


def format_duration(total_seconds: int) -> str:
    """Return a duration as hours and minutes, like ``2h 05m``.

    Args:
        total_seconds: How long the job ran, in seconds.

    Returns:
        The hours and the zero-padded minutes.
    """
    hours, remaining_seconds = divmod(total_seconds, 3600)
    return f"{hours}h {remaining_seconds // 60:02d}m"
