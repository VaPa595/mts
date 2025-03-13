import MetaTrader5 as mt5

from finance.datasource.downloader import CandleHistDownloader
from finance.utilities.utime import now_utc_epoch, utc_epoch_ms_to_sec


class ForexCandleHistDownloader(CandleHistDownloader):

    def __init__(self, data_converter, symbol, data_frames_dict=None):
        """
        :param finance.datasource.converter.MarketDataConverter data_converter:
        :param str symbol:
        :param data_frames_dict:  # todo[1]
        """
        super().__init__(data_converter, data_frames_dict)
        self.__symbol = symbol

    def download_hist(self, candle_interval, start_time, end_time=None):
        """
        Downloading and returning histories of raw candles
        Note:
        1- Returned data only contains OpenTime not CloseTime,
        2- OpenTime is in second, so, should be converted to
         millisecond if is necessary(we don't do conversion in this method to follow SOLID principles).
        :param str candle_interval: interval of the candle (binance form): i.e. 1m, 15m, 1h, 4h
        :param int start_time: start time of the history in UTC epoch in millisecond
        :param int end_time: end time of the history in UTC epoch in millisecond
        :return:
        :rtype: list[list[str]]
        """
        #  establish connection to MetaTrader 5 terminal
        if not mt5.initialize():
            print("initialize() failed, error code =", mt5.last_error())
            quit()

        # NOTE: start_time and end_time are given in millisecond, but in mt5.copy_rates_range these times are required
        #       in second. So, should be converted.
        if end_time is None:
            end_time = now_utc_epoch()  # note that it downloads the candle with OpenTime equal to end_time

        start_time_in_sec = utc_epoch_ms_to_sec(start_time)
        end_time_in_sec = utc_epoch_ms_to_sec(end_time)
        print("Start to download (forex) history " + candle_interval + " ...")
        frx_candle_int = self.bin_to_frx_interval(candle_interval)
        history = mt5.copy_rates_range(self.__symbol, frx_candle_int, start_time_in_sec, end_time_in_sec)

        print("History (forex) " + candle_interval + " downloaded.")
        # if not verify_history(history, candle_interval, start_time, end_time):
        #     raise Exception("Invalid downloaded history.")
        return history

    @staticmethod
    def bin_to_frx_interval(bin_interval):  # todo (2) it now exists in common.py
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
