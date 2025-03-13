from finance.datasource.sockets import CandleSocket
from finance.datasource.converter import MarketDataConverter
from finance.datasource.downloader import CandleHistDownloader


class DataSource:
    def __init__(self, name, candle_socket, candle_hist_downloader, data_converter):
        """
        :param str name:
        :param CandleSocket candle_socket:
        :param CandleHistDownloader candle_hist_downloader:
        :param MarketDataConverter data_converter:
        """
        self.__name = name
        self.__socket = candle_socket
        self.__candle_hist_downloader = candle_hist_downloader
        self.__data_converter = data_converter

    def init_candle_socket(self):
        self.__socket.init()

    def start_candle_socket(self, callback, symbol, candle_interval):
        self.__socket.start(callback, symbol, candle_interval)

    def stop_candle(self):
        self.__socket.stop()

    # todo (2) Now separate modules download_raw_hist and get_df_hist are used as public methods in Converter. Those could be called from this class
    # old_todo (1): return types in various market are not the same, so, for now, I remove this feature
    # def get_raw_history(self, candle_interval, start_time, end_time=None):  # detailed candles
    #     """
    #     :param str candle_interval: interval of the candle: i.e. 1m, 15m, 1h, 4h
    #     :param int start_time: start time of the history in UTC epoch
    #     :param int or None end_time: end time of the history in UTC epoch
    #     :return:
    #     :rtype: list[list[str]]
    #     """
    #     return self.__candle_hist_downloader.get_raw_history(candle_interval, start_time, end_time)

    def get_candle_history(self, candle_interval, start_time, end_time=None):
        """
        Downloading historical candles of candle_interval in [start_time end_time] and converting to simple Candle
        :param str candle_interval: interval of the candle: i.e. 1m, 15m, 1h, 4h
        :param int start_time: start time of the history in UTC epoch
        :param int end_time: end time of the history in UTC epoch
        :return:
        :rtype: list[finance.models.candles.Candle]
        """
        return self.__candle_hist_downloader.get_candle_history(candle_interval, start_time, end_time)

    # IMPORTANT: This method has been removed, see the reason in MarketDataConverter
    # def df_candle_to_candle_object(self, raw_candle, candle_interval):  # old_todo(00)
    #     """
    #     :param list[str] raw_candle: [OpenTime, Open, High, Low, Close, Volume, CloseTime, ...] (maybe in json format)
    #     :param str candle_interval:
    #     :return:
    #     :rtype: finance.models.candles.Candle
    #     """
    #     return self.__raw_data_converter.df_candle_to_candle_object(raw_candle, candle_interval)

    def df_hist_to_candle_object_hist(self, df_hist, candle_interval):
        """
        :param pandas.DataFrame df_hist:
        :param str candle_interval:
        :return:
        :rtype: list[finance.models.candles.Candle]
        """
        return self.__data_converter.df_hist_to_candle_object_hist(df_hist, candle_interval)

    def get_candle(self, candle_interval, open_time):
        """
        Download single raw candle and convert it to candle object then return
        :param str candle_interval:
        :param int open_time:
        :return:
        :rtype: finance.models.candles.Candle
        """
        return self.__candle_hist_downloader.get_candle(candle_interval, open_time)

    def get_data_frames_dict(self):
        return self.__candle_hist_downloader.get_data_frames_dict()

    def df_hist_to_socket_candle_hist(self, df_hist):
        """
        Converting a DataFrame of candles to list of candles sent by market socket
        :param pandas.DataFrame df_hist:
        :return: list of JSON
        :rtype: list[str]
        """
        return self.__data_converter.df_hist_to_socket_candle_hist(df_hist)
