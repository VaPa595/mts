import time
from datetime import datetime, timezone, timedelta


def now_utc_epoch(ms=True):
    if ms:
        return int(1000*datetime.utcnow().replace(tzinfo=timezone.utc).timestamp())  # millisecond
    return int(datetime.utcnow().replace(tzinfo=timezone.utc).timestamp())  # second


def epoch_to_datetime(epoch, datetime_format=None):
    if datetime_format is None:
        datetime_format = "%Y.%m.%d %H:%M:%S"
    return datetime.fromtimestamp(epoch/1000).strftime(datetime_format)


def epoch_to_utc_datetime(epoch, datetime_format=None):  # todo
    if datetime_format is None:
        datetime_format = "%Y.%m.%d %H:%M:%S"
    return datetime.utcfromtimestamp(epoch/1000).strftime(datetime_format)


def datetime_to_epoch(datetime_str, datetime_format, ms=True):  # don't use default datetime_format
    datetime_obj = datetime.strptime(datetime_str, datetime_format)
    if ms:
        return int(datetime_obj.timestamp()*1000)  # in milli seconds
    return int(datetime_obj.timestamp())  # in second


def utc_datetime_to_epoch(datetime_str, datetime_format, ms=True):
    datetime_obj = datetime.strptime(datetime_str, datetime_format)
    if ms:
        return int(datetime_obj.replace(tzinfo=timezone.utc).timestamp()*1000)  # in milli seconds
    return int(datetime_obj.replace(tzinfo=timezone.utc).timestamp())  # in seconds


def now_for_file_name(datetime_format=None):
    if datetime_format is None:
        datetime_format = "%Y-%m-%d-%H-%M-%S-%f"
    return datetime.now().strftime(datetime_format)


def forward_date_time_str(date_time_str, minutes, date_time_format):  # don't use default datetime_format
    date_time_obj = datetime.strptime(date_time_str, date_time_format)
    forwarded_date_time = date_time_obj + timedelta(minutes=minutes)
    return forwarded_date_time.strftime(date_time_format)


def utc_epoch_ms_to_sec(utc_time):
    return int(utc_time/1000)  # Note: int() only removes floating point part without rounding.


class TicToc:
    def __init__(self):
        self.__start = None

    def tic(self):
        self.__start = time.time()

    def toc(self):
        return time.time() - self.__start


