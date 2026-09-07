from datetime import datetime, timezone


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def as_utc(dt: datetime) -> datetime:
    """Normalise to timezone-aware UTC. Naive datetimes are assumed UTC."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def skew_seconds(a: datetime, b: datetime) -> float:
    return abs((as_utc(a) - as_utc(b)).total_seconds())
