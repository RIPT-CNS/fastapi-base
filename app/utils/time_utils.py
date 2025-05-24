from datetime import datetime, timedelta, timezone


def timestamp_now() -> float:
    return datetime.now(timezone.utc).timestamp()


def timestamp_to_datetime(timestamp: float) -> datetime:
    return datetime.fromtimestamp(timestamp, tz=timezone.utc)


def datetime_to_timestamp(dt: datetime) -> float:
    return dt.timestamp()


def datetime_now() -> datetime:
    return datetime.now(timezone.utc)


def datetime_to_str(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def str_to_datetime(date_str: str) -> datetime:
    return datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)


def str_to_timestamp(date_str: str) -> float:
    dt = str_to_datetime(date_str)
    return datetime_to_timestamp(dt)


def timestamp_to_str(timestamp: float) -> str:
    dt = timestamp_to_datetime(timestamp)
    return datetime_to_str(dt)


def timestamp_after_now(
    seconds: int = 0,
    minutes: int = 0,
    hours: int = 0,
    days: int = 0,
    months: int = 0,
    years: int = 0,
) -> float:
    datetime_now_tmp = datetime_now()
    delta = timedelta(
        seconds=seconds,
        minutes=minutes,
        hours=hours,
        days=days + months * 30 + years * 365,
    )
    new_datetime = datetime_now_tmp + delta
    return datetime_to_timestamp(new_datetime)


def timestamp_before_now(
    seconds: int = 0,
    minutes: int = 0,
    hours: int = 0,
    days: int = 0,
    months: int = 0,
    years: int = 0,
) -> float:
    datetime_now_tmp = datetime_now()
    delta = timedelta(
        seconds=seconds,
        minutes=minutes,
        hours=hours,
        days=days + months * 30 + years * 365,
    )
    new_datetime = datetime_now_tmp - delta
    return datetime_to_timestamp(new_datetime)
