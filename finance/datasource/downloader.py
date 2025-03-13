from abc import ABC, abstractmethod
from finance.datasource.converter import MarketDataConverter
from finance.utilities.ufinance import common


class CandleHistDownloader(ABC):

    def __init__(self, data_converter, data_frames_dict=None):
        """
        :param MarketDataConverter data_converter:
        """
        self._data_converter = data_converter
        self._data_frames_dict = data_frames_dict

        # -------------------------------------------------------------------------------------------
        # **** Note: data_frame and directly downloaded data from api should have same structure ****
        # -------------------------------------------------------------------------------------------

    # IMPORTANT: Now separate modules download_raw_hist and get_df_hist are used as public methods
    # old_todo (1): return type in various market are not the same, so, for now, I make this method private
    # @abstractmethod
    # def __get_raw_history(self, candle_interval, start_time, end_time=None):  # detailed candles
    #     """
    #     Returning histories of raw candles
    #     :param str candle_interval: interval of the candle: i.e. 1m, 15m, 1h, 4h
    #     :param int start_time: start time of the history in UTC epoch
    #     :param int end_time: end time of the history in UTC epoch
    #     :return:
    #     :rtype:
    #     """
    #     pass

    def get_candle_history(self, candle_interval, start_time, end_time=None):
        """
        Returning historical candles of candle_interval in [start_time end_time] and converting to simple Candle
        :param str candle_interval: interval of the candle: i.e. 1m, 15m, 1h, 4h
        :param int start_time: start time of the history in UTC epoch
        :param int end_time: end time of the history in UTC epoch
        :return:
        :rtype: list[finance.models.candles.Candle]
        """
        try:
            if self._data_frames_dict is None:
                down_hist = self.download_hist(candle_interval, start_time, end_time)
                return self._data_converter.down_hist_to_candle_object_hist(down_hist, candle_interval)
            else:
                df_hist = self.get_df_hist(candle_interval, start_time, end_time)
                return self._data_converter.df_hist_to_candle_object_hist(df_hist, candle_interval)
        except Exception as e:
            log_msg = f"Exception in getting candle history -- Interval: {candle_interval}, start: {start_time}, end: {end_time}, "
            print(log_msg)
            raise Exception("Downloader: " + str(e))

    def get_candle(self, candle_interval, open_time):
        """
        Returning converted single candle data to candle object
        :param str candle_interval:
        :param int open_time:
        :return:
        :rtype: finance.models.candles.Candle
        """
        # raw_candle = self.__all_data_frames_dict[candle_interval].loc[open_time]  # this is handled in __get_from_data_frame
        close_time = common.calculate_candle_close_time(candle_interval, open_time)  # close_time is just used to get only the requested candle not next ones

        if self._data_frames_dict is None:
            down_hist = self.download_hist(candle_interval, open_time, close_time)  # hist with one element
            candle_hist = self._data_converter.down_hist_to_candle_object_hist(down_hist, candle_interval)  # a list with one candle object
        else:
            df_hist = self.get_df_hist(candle_interval, open_time, close_time)  # df with one element
            candle_hist = self._data_converter.df_hist_to_candle_object_hist(df_hist, candle_interval)  # a list with one candle object

        return candle_hist[0]

    @abstractmethod
    def download_hist(self, candle_interval, start_time, end_time=None):  # todo (1): return types varies market to market
        """
        Downloading and returning histories of candles
        :param str candle_interval: interval of the candle: i.e. 1m, 15m, 1h, 4h
        :param int start_time: start time of the history in UTC epoch
        :param int end_time: end time of the history in UTC epoch
        :return:
        :rtype:
        """
        pass

    def get_df_hist(self, candle_interval, start_time, end_time=None):
        """
        Getting historical candles of candle_interval in [start_time end_time] from data frame
        :param str candle_interval: interval of the candle: i.e. 1m, 15m, 1h, 4h
        :param int start_time: start time of the history in UTC epoch
        :param int end_time: end time of the history in UTC epoch
        :return:
        :rtype: pandas.DataFrame
        """
        if start_time is not None and end_time is not None:
            print("Get (binance) history " + candle_interval + " from data_frame ...")
            return self._data_frames_dict[candle_interval].loc[start_time:end_time]
        if start_time is not None:
            return self._data_frames_dict[candle_interval].loc[start_time:]
        raise Exception(f"Invalid interval for history: start_time={start_time}, end_time={end_time}")

    def get_data_frames_dict(self):
        return self._data_frames_dict
