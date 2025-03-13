from finance.utilities import utime
from finance.utilities.ufinance import common
from finance.utilities.uio import uio, uexcel
from finance.utilities.utime import now_utc_epoch, utc_epoch_ms_to_sec
import MetaTrader5 as mt5
import numpy as np


def down_frx_hist(symbol, candle_interval, start_date, end_date=None):
    """
    Downloading and returning histories of raw candles
    Note:
    1- Returned data only contains OpenTime not CloseTime,
    2- OpenTime is in second, so, should be converted to
     millisecond if is necessary(we don't do conversion in this method to follow SOLID principles).
    :param str symbol: the symbol of market
    :param str candle_interval: interval of the candle (binance form): i.e. 1m, 15m, 1h, 4h
    :param int start_date: start time of the history in UTC epoch in millisecond
    :param int end_date: end time of the history in UTC epoch in millisecond
    :return:
    :rtype: list[list[str]]
    """
    #  establish connection to MetaTrader 5 terminal
    if not mt5.initialize():
        print("initialize() failed, error code =", mt5.last_error())
        quit()

    # NOTE: start_date and end_date are given in millisecond, but in mt5.copy_rates_range these times are required
    #       in second. So, should be converted.
    if end_date is None:
        end_date = now_utc_epoch()  # note that it downloads the candle with OpenTime equal to end_date

    start_date_in_sec = utc_epoch_ms_to_sec(start_date)
    end_date_in_sec = utc_epoch_ms_to_sec(end_date)
    print("Start to download (forex) history " + candle_interval + " ...")
    frx_candle_int = common.bin_to_frx_interval(candle_interval)
    history = mt5.copy_rates_range(symbol, frx_candle_int, start_date_in_sec, end_date_in_sec)

    print("History (forex) " + candle_interval + " downloaded.")
    # if not verify_history(history, candle_interval, start_date, end_date):
    #     raise Exception("Invalid downloaded history.")
    return history


def down_and_save_frx_hist(symbol, candle_interval, start_date, end_date=None, file_name=None):
    hist = down_frx_hist(symbol, candle_interval, start_date, end_date)
    headers = 'OpenTime, Open,	High, Low, Close, TickVolume, Spread, RealVolume'
    csv_file = uio.abs_data_file_path(file_name) if file_name is not None else uio.abs_data_file_path(f"forex_kline-{candle_interval}-{start_date}-{end_date}.csv")
    np.savetxt(csv_file, hist, delimiter=',', header=headers, fmt='%s', comments='')


def main():
    symbol = "BTCUSD"
    candle_interval = "1m"
    start_date = utime.utc_datetime_to_epoch("2023.06.18 00:00:00", "%Y.%m.%d %H:%M:%S")
    end_date = None  # utime.utcdatetime_to_epoch()
    down_and_save_frx_hist(symbol, candle_interval, start_date, end_date)


if __name__ == '__main__':
    main()
