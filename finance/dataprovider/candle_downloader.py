# -------------------------------------------------
# ************ NOT USED ANY MORE ******************
# -------------------------------------------------

# from binance import Client
#
# from finance.modules.enums import BINANCE, FOREX, DF_BINANCE, DF_FOREX
# from finance.utilities.ufinance import common
#
#
# # todo (2): is appropriate name for downloading methods?
#
#
# class HistoricalCandlesDownloader:
#     # todo (3): do something like (source, params) --> then init instance variables accordingly.
#     # for offline source, consider separate excel file for each candle_interval (some may be None, except 1m), although
#     # it is not needed right now.
#     def __init__(self, source, symbol, market_config=None, all_data_frames_dic=None):
#         self.symbol = symbol
#         self.__source = source
#         if source == BINANCE:
#             self.__api_key = market_config.api_key
#             self.__api_secret = market_config.api_secret
#         elif source == DF_BINANCE or source == DF_FOREX:
#             self.__all_data_frames_dic = all_data_frames_dic
#         # todo (1) forex setting
#
#     def get_raw_history(self, candle_interval, start_time, end_time=None):  # detailed candles
#         # todo (1): IMP, return types
#         if self.__source == BINANCE:
#             return self.__download_from_binance(candle_interval, start_time, end_time)
#         if self.__source == BINANCE:
#             return self.__download_from_forex(candle_interval, start_time, end_time)
#         if self.__source == DF_BINANCE or self.__source == DF_FOREX:
#             return self.__read_from_data_frame(candle_interval, start_time, end_time)
#
#     def get_candle_history(self, candle_interval, start_time, end_time=None):
#         """
#         Downloading historical candles of candle_interval in [start_time end_time] and converting to simple Candle
#         :param str candle_interval: interval of the candle: i.e. 1m, 15m, 1h, 4h
#         :param int start_time: start time of the history in UTC epoch
#         :param int end_time: end time of the history in UTC epoch
#         :return
#         :rtype list[Candle]
#         """
#         raw_hist = self.get_raw_history(candle_interval, start_time, end_time)  # list[list[str]]
#         # raw_candle: OpenTime, Open, High, Low, Close, Volume, CloseTime, ...
#         candle_hist = common.raw_hist_to_candle_object_hist(self.__source, raw_hist, candle_interval)
#         return candle_hist
#
#     def __download_from_forex(self, candle_interval, start_time, end_time):
#         #
#         pass
#
#     def __read_from_data_frame(self, candle_interval, start_time, end_time=None):
#         # todo (4): IMP: flexible regarding to change in config??
#         """
#         Reading historical candles of candle_interval in [start_time end_time] from data frame
#         :param str candle_interval: interval of the candle: i.e. 1m, 15m, 1h, 4h
#         :param int start_time: start time of the history in UTC epoch
#         :param int end_time: end time of the history in UTC epoch
#         """
#         if start_time is not None and end_time is not None:
#             hist_as_df = self.__all_data_frames_dic[candle_interval].loc[start_time:end_time]
#             hist_as_np = hist_as_df.to_numpy()
#             return hist_as_np
#         if start_time is not None:
#             hist_as_df = self.__all_data_frames_dic[candle_interval].loc[start_time:]
#             hist_as_np = hist_as_df.to_numpy()
#             return hist_as_np
#         raise Exception(f"Invalid interval for downloading history: start_time={start_time}, end_time={end_time}")
#
#     def get_candle_by_open_time(self, candle_interval,
#                                 open_time):  # todo (1): for readability and generality in future, first check data source (don't consider it only for offline usage)
#         """
#         Only for offline mode, retrieving from __all_data_frames_dic
#         :param str candle_interval:
#         :param int open_time:
#         :return:
#         :rtype Candle:
#         """
#         raw_candle = self.__all_data_frames_dic[candle_interval].loc[open_time]
#         candle = common.raw_candle_to_candle_object(self.__source, raw_candle, candle_interval)
#         return candle

