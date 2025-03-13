import math
from collections import deque

import MetaTrader5 as mt5
import pandas as pd
from binance.enums import KLINE_INTERVAL_1MINUTE, KLINE_INTERVAL_15MINUTE, KLINE_INTERVAL_1HOUR, KLINE_INTERVAL_4HOUR

from finance.models.candles import Candle1m, Candle15m, Candle1h, Candle4h, Candle
# from finance.modules.enums import BINANCE, DF_BINANCE, FOREX, DF_FOREX
from finance.utilities import umath
from finance.utilities.utime import TicToc

tic_toc = TicToc()


def get_candle_model(candle_interval):  # todo: use CandleModel in usages
    """
    :param str candle_interval:
    :return:
    :rtype: mongoengine.base.metaclasses.TopLevelDocumentMetaclass
    """
    if candle_interval == KLINE_INTERVAL_1MINUTE:
        return Candle1m
    elif candle_interval == KLINE_INTERVAL_15MINUTE:
        return Candle15m
    elif candle_interval == KLINE_INTERVAL_1HOUR:
        return Candle1h
    elif candle_interval == KLINE_INTERVAL_4HOUR:
        return Candle4h
    else:
        raise Exception("Invalid candle_interval: " + candle_interval)


def create_hist_str(history):  # todo more readable and usable
    """
    :param deque[Candle] history:
    """
    hist_str = ""
    count = 0
    while count < len(history) - 1:
        hist_str = hist_str + history[count].__str__() + "\n"
        count += 1
    hist_str = hist_str + history[count].__str__()
    return hist_str


# ---------- Candle Related ----------

def find_candle_color(candle):
    """
    :param Candle candle:
    :return:
    :rtype: int
    """
    if umath.is_less_or_equal(candle.open, candle.close):  # todo (1): IMP, if == happens its a doji --> return green
        color = 1
    else:
        color = -1
    return color


def is_red_candle(candle_4h):
    return find_candle_color(candle_4h) == -1


def is_green_candle(candle_4h):
    return find_candle_color(candle_4h) == 1


# todo (1): IMP, how to test this?
def get_all_candles_from_hist_1m(hist_1m, candle_interval):
    """
    :param deque[Candle] hist_1m:
    :param str candle_interval:
    :return:
    :rtype: list[Candle]
    """
    candles = []
    candle_len = candle_interval_in_minutes(candle_interval)
    start_index = get_first_tick_index(hist_1m, candle_interval)
    if start_index >= 0:
        end_index = start_index + candle_len - 1
        while end_index < len(hist_1m):
            candle = create_candle_from_hist_1m(hist_1m, candle_interval, start_index, end_index)
            candles.append(candle)
            start_index = end_index + 1
            end_index = start_index + candle_len - 1
    return candles


def get_first_tick_index(hist_1m, candle_interval):
    """
    :param deque[Candle] hist_1m:
    :param str candle_interval:
    :return:
    :rtype: int
    """
    for i in range(len(hist_1m)):
        open_time = hist_1m[i].open_time
        if is_tick(open_time, candle_interval):
            return i
    return -1


# todo (1): IMP, len(hist_1m) shows which candle should be created, no need to candle interval
def create_candle_from_hist_1m(hist_1m, candle_interval, start_index=0, end_index=None):  # don't use end_index = -1
    """
    :param deque[Candle] hist_1m:
    :param int start_index:
    :param int end_index:
    :param str candle_interval:
    :return:
    :rtype: Candle or None
    """
    if len(hist_1m) == 0:
        return None

    if end_index is None:
        end_index = len(hist_1m) - 1

    first_candle_1m = hist_1m[start_index]
    last_candle_1m = hist_1m[end_index]
    high = first_candle_1m.high
    low = first_candle_1m.low
    volume = first_candle_1m.volume
    for i in range(start_index + 1, end_index):  # between start and end
        candle1m = hist_1m[i]
        if high < candle1m.high:
            high = candle1m.high
        if low > candle1m.low:
            low = candle1m.low
        volume = volume + candle1m.volume

    # todo (3): IMP2, is it possible to first create a Candle then convert it to Candle1h, or Candle4h, or, ...
    # todo (2): flexible to change in config
    if candle_interval == KLINE_INTERVAL_15MINUTE:
        return Candle15m(open=first_candle_1m.open, high=high, low=low, close=last_candle_1m.close, volume=volume,
                         open_time=first_candle_1m.open_time, close_time=last_candle_1m.close_time)
    if candle_interval == KLINE_INTERVAL_1HOUR:
        return Candle1h(open=first_candle_1m.open, high=high, low=low, close=last_candle_1m.close, volume=volume,
                        open_time=first_candle_1m.open_time, close_time=last_candle_1m.close_time)
    if candle_interval == KLINE_INTERVAL_4HOUR:
        return Candle4h(open=first_candle_1m.open, high=high, low=low, close=last_candle_1m.close, volume=volume,
                        open_time=first_candle_1m.open_time, close_time=last_candle_1m.close_time)
    raise Exception("Unexpected candle interval")


def calc_last_tick_epoch(candle_interval, current_time):  # todo(2) check that it has been correctly renamed
    interval_in_ms = candle_interval_in_millisecond(candle_interval)
    tick = (math.floor(current_time / interval_in_ms) - 1) * interval_in_ms
    return tick


def candle_interval_in_millisecond(candle_interval):
    """
    :param str candle_interval:
    :return:
    :rtype: int
    """
    if candle_interval == KLINE_INTERVAL_1MINUTE:
        return 60 * 1000
    if candle_interval == KLINE_INTERVAL_15MINUTE:
        return 15 * 60 * 1000
    if candle_interval == KLINE_INTERVAL_1HOUR:
        return 60 * 60 * 1000
    if candle_interval == KLINE_INTERVAL_4HOUR:
        return 4 * 60 * 60 * 1000
    raise Exception("Unexpected candle_interval: " + candle_interval)


def candle_interval_in_minutes(candle_interval):
    """
    :param str candle_interval:
    :return:
    :rtype: int
    """
    if candle_interval == KLINE_INTERVAL_1MINUTE:
        return 1
    if candle_interval == KLINE_INTERVAL_15MINUTE:
        return 15
    if candle_interval == KLINE_INTERVAL_1HOUR:
        return 60
    if candle_interval == KLINE_INTERVAL_4HOUR:
        return 240
    raise Exception("Unexpected candle_interval: " + candle_interval)


def calc_diff_two_candles(candle_interval, candle1, candle2):  # todo (3): rename (also parameters)
    """
    :param str candle_interval:
    :param Candle candle1:
    :param Candle candle2:
    :return:
    :rtype: int
    """
    return int((candle2.open_time - candle1.open_time) / candle_interval_in_millisecond(candle_interval))


def are_candles_consecutive(candle_interval, last_candle, new_candle):
    """
    :param str candle_interval:
    :param Candle last_candle:
    :param Candle new_candle:
    :return:
    :rtype: bool
    """
    return new_candle.open_time - last_candle.open_time == candle_interval_in_millisecond(candle_interval)


def candle_broke_sline(candle, hline, breaking_threshold):
    """
    It does not return direction of the break
    :param Candle candle:
    :param float hline:
    :param float breaking_threshold:
    :return:
    :rtype: bool
    """
    if umath.are_equal(candle.open, candle.close):
        print(f"Doji candle at: {candle.open_time}")
        return False
    return umath.is_greater_or_equal((candle.close - hline) / (candle.close - candle.open), breaking_threshold)


def calculate_candle_close_time(candle_interval, open_time):
    """
    :param str candle_interval:
    :param int open_time: epoch in millisecond
    :return: epoch in millisecond
    :rtype: int
    """
    return open_time + candle_interval_in_millisecond(candle_interval) - 1


# ---------- Time and Ticks ------------
def get_ticks(epoch_time):
    """
    :param int epoch_time:
    :return:
    :rtype: list(str)
    """
    ticks = []
    if epoch_time % 900000 == 0:  # 15m
        ticks.append(KLINE_INTERVAL_15MINUTE)
    if epoch_time % 3600000 == 0:  # 1h
        ticks.append(KLINE_INTERVAL_1HOUR)
    if epoch_time % 14400000 == 0:  # 4h
        ticks.append(KLINE_INTERVAL_4HOUR)
    return ticks


def is_tick_4h(epoch_time):
    return epoch_time % 14400000 == 0


def get_tick_times_in_interval(candle_interval, start, end):
    tick_times = []
    tick_len = candle_interval_in_millisecond(candle_interval)
    first_tick = int(math.ceil(start / tick_len) * tick_len)
    if first_tick < end:
        tick_times.append(first_tick)
        next_tick = first_tick + tick_len
        while next_tick < end:
            tick_times.append(next_tick)
            next_tick = next_tick + tick_len
    return tick_times


def is_tick(epoch_time, candle_interval):
    """
    :param int epoch_time:
    :param str candle_interval:
    :return:
    :rtype: bool
    """
    if candle_interval == KLINE_INTERVAL_15MINUTE:
        return epoch_time % 900000 == 0
    if candle_interval == KLINE_INTERVAL_1HOUR:
        return epoch_time % 3600000 == 0
    if candle_interval == KLINE_INTERVAL_4HOUR:
        return epoch_time % 14400000 == 0
    raise Exception(f"Unexpected candle_interval: {candle_interval}")


# ----- deque history of candles -----

def hist_to_data_frame(hist):  # list or deque of candles
    hist_as_dict = [candle.to_dict() for candle in hist]
    return pd.DataFrame(hist_as_dict)


def get_df_hist_field_data(pd_data_frame, field):
    """
    only for histories as pd.DataFrame
    :param pd.DataFrame pd_data_frame:
    :param str field:
    :return:
    :rtype: pd.DataFrame
    """
    return pd_data_frame.loc[:, field]


# ------ Moving Average -------
def exp_mov_avg_on_list_hist(hist, field, span):  # list of deque of candles  # todo (4): docstring
    hist_as_df = hist_to_data_frame(hist)
    return exp_mov_avg(get_df_hist_field_data(hist_as_df, field), span)


def exp_mov_avg_on_df_hist(df_hist, field, span):
    return exp_mov_avg(get_df_hist_field_data(df_hist, field), span)


def exp_mov_avg(pd_data_frame, span):
    ema = pd_data_frame.ewm(span=span, adjust=False).mean()
    return ema


def get_ema_dir(ema, dir_interval):  # it is valid only if ema is a Series (2D) object not DataFrame
    diff = ema.iloc[-1] - ema.iloc[-dir_interval]
    if diff > 0:
        ema_dir = 1  # positive
    elif diff < 0:
        ema_dir = -1  # negative
    else:
        ema_dir = 0  # it is constant in the interval
    return ema_dir


def get_ema_dir_on_df_hist(df_hist, field, span, dir_interval):
    ema = exp_mov_avg_on_df_hist(df_hist, field, span)
    ema_dir = get_ema_dir(ema, dir_interval)
    return ema_dir


# ---- Convert raw candle(s) to candle object(s) ----

# todo (1): raw_candle may be either data_frame or list[str], ... docstring ... we couldn't use name of the columns because not always are df some times are list

# def raw_candle_to_candle_object(data_source, raw_candle, candle_interval):
#     """
#     :param str data_source: see enums.py
#     :param list[str] raw_candle: [OpenTime, Open, High, Low, Close, Volume, CloseTime, ...]
#     :param str candle_interval:
#     :return:
#     :rtype: Candle
#     """
#     if data_source == BINANCE or data_source == DF_BINANCE:
#         return binance_raw_candle_to_candle_object(raw_candle, candle_interval)
#     elif data_source == FOREX or data_source == DF_FOREX:
#         return forex_raw_candle_to_candle_object(raw_candle, candle_interval)
#     else:
#         raise Exception(f"Invalid data source: {data_source}")
#
#
# def raw_hist_to_candle_object_hist(data_source, raw_hist, candle_interval):
#     """
#     :param str data_source: see enums.py
#     :param list[list[str]] raw_hist: raw_candle: [OpenTime, Open, High, Low, Close, Volume, CloseTime, ...]
#     :param str candle_interval:
#     :return:
#     :rtype: list[Candle]
#     """
#     if data_source == BINANCE or data_source == DF_BINANCE:
#         return binance_raw_hist_to_candle_object_hist(raw_hist, candle_interval)
#     elif data_source == FOREX or data_source == DF_FOREX:
#         return forex_raw_hist_to_candle_object_hist(raw_hist, candle_interval)
#     else:
#         raise Exception(f"Invalid data source: {data_source}")


# def binance_raw_candle_to_candle_object(raw_candle, candle_interval):
#     """
#     :param list[str] raw_candle: raw_candle: [OpenTime, Open, High, Low, Close, Volume, CloseTime, ...]
#     :param str candle_interval:
#     :return:
#     :rtype: Candle
#     """
#     candle_model = get_candle_model(candle_interval)
#
#     candle = candle_model(open=raw_candle[1], high=raw_candle[2], low=raw_candle[3],
#                           close=raw_candle[4], volume=raw_candle[5], open_time=raw_candle[0],
#                           close_time=raw_candle[6])
#     return candle


# def forex_raw_candle_to_candle_object(raw_candle, candle_interval):
#     """
#     :param list[str] raw_candle: raw_candle: [OpenTime, Open, High, Low, Close, Volume, CloseTime, ...]
#     :param str candle_interval:
#     :return:
#     :rtype: Candle
#     """
#     candle_model = get_candle_model(candle_interval)
#
#     candle = candle_model(open=raw_candle[2], high=raw_candle[3], low=raw_candle[4],
#                           close=raw_candle[5], volume=raw_candle[6], open_time=raw_candle[7],
#                           close_time=raw_candle[8])
#     return candle


# def binance_raw_hist_to_candle_object_hist(raw_hist, candle_interval):
#     """
#     :param list[list[str]] raw_hist: raw_candle: [OpenTime, Open, High, Low, Close, Volume, CloseTime, ...]
#     :param str candle_interval:
#     :return:
#     :rtype: list[Candle]
#     """
#
#     candle_model = get_candle_model(candle_interval)
#
#     candle_object_hist = [candle_model(open=raw_candle[1], high=raw_candle[2], low=raw_candle[3],
#                                        close=raw_candle[4], volume=raw_candle[5], open_time=raw_candle[0],
#                                        close_time=raw_candle[6]) for raw_candle in raw_hist]
#
#     return candle_object_hist


# def forex_raw_hist_to_candle_object_hist(raw_hist, candle_interval):
#     """
#     :param list[list[str]] raw_hist: raw_candle: [OpenTime, Open, High, Low, Close, Volume, CloseTime, ...]
#     :param str candle_interval:
#     :return:
#     :rtype: list[Candle]
#     """
#     candle_model = get_candle_model(candle_interval)
#
#     candle_object_hist = [candle_model(open=raw_candle[2], high=raw_candle[3], low=raw_candle[4],
#                                        close=raw_candle[5], volume=raw_candle[6], open_time=raw_candle[7],
#                                        close_time=raw_candle[8]) for raw_candle in raw_hist]
#
#     return candle_object_hist


def df_candle_to_obj_candle(df_candle, candle_interval):
    """
    candle_as_df to Candle object
    :param pd.DataFrame df_candle:
    :param str candle_interval:
    :return:
    :rtype: Candle
    """

    candle_model = get_candle_model(candle_interval)

    # Note: because we already know that it is a df, so we don't need indexes, we could use name of the columns
    # Also note that hear we considered a df that is constructed from Candle, so its column name is the same as Candle attributes
    return candle_model(open=df_candle.open, high=df_candle.high, low=df_candle.low,
                        close=df_candle.close, volume=df_candle.volume, open_time=df_candle.open_time,
                        close_time=df_candle.close_time)


def bin_to_frx_interval(bin_interval):
    if bin_interval == "1m":
        return mt5.TIMEFRAME_M1
    elif bin_interval == "3m":
        return mt5.TIMEFRAME_M3
    elif bin_interval == "5m":
        return mt5.TIMEFRAME_M5
    elif bin_interval == "15m":
        return mt5.TIMEFRAME_M15
    elif bin_interval == "30m":
        return mt5.TIMEFRAME_M30
    elif bin_interval == "1h":
        return mt5.TIMEFRAME_H1
    elif bin_interval == "2h":
        return mt5.TIMEFRAME_H2
    elif bin_interval == "4h":
        return mt5.TIMEFRAME_H4
    elif bin_interval == "6h":
        return mt5.TIMEFRAME_H6
    elif bin_interval == "8h":
        return mt5.TIMEFRAME_H8
    elif bin_interval == "12h":
        return mt5.TIMEFRAME_H12
    elif bin_interval == "1d":
        return mt5.TIMEFRAME_D1
    elif bin_interval == "1w":
        return mt5.TIMEFRAME_W1
    elif bin_interval == "1M":  # todo (1): case sensitive?
        return mt5.TIMEFRAME_MN1
    raise Exception(f"Invalid candle interval for Forex: {bin_interval}")