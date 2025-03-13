from binance import Client

from finance.datasource.downloader import CandleHistDownloader


class BinanceCandleHistDownloader(CandleHistDownloader):

    def __init__(self, data_converter, api_key, api_secret, symbol, data_frames_dict=None):
        """
        :param finance.datasource.converter.MarketDataConverter data_converter:
        :param str api_key: 
        :param str api_secret: 
        :param str symbol: 
        :param data_frames_dict: 
        """
        super().__init__(data_converter, data_frames_dict)
        self.__api_key = api_key
        self.__api_secret = api_secret
        self.__symbol = symbol

        # todo(2): api_key, api_secret, symbol be given on each call?

    # IMPORTANT: Now separate modules download_hist and get_df_hist are used as public methods
    # # old_todo (1): return types in various market are not the same, so, for now, I remove this feature
    # def __get_raw_history(self, candle_interval, start_time, end_time=None):  # detailed candles
    #     """
    #     Returning histories of raw candles
    #     :param str candle_interval: interval of the candle: i.e. 1m, 15m, 1h, 4h
    #     :param int start_time: start time of the history in UTC epoch
    #     :param int end_time: end time of the history in UTC epoch
    #     :return:
    #     :rtype: list[list[str]]
    #     """
    #
    #     if self._data_frames_dict is None:
    #         return self.__download_hist(candle_interval, start_time, end_time)
    #     return self.__get_df_hist(candle_interval, start_time, end_time)

    def download_hist(self, candle_interval, start_time, end_time=None):
        """
        Downloading and returning histories of candles
        :param str candle_interval: interval of the candle: i.e. 1m, 15m, 1h, 4h
        :param int start_time: start time of the history in UTC epoch
        :param int end_time: end time of the history in UTC epoch
        :return:
        :rtype: list[list[str]]
        """
        print("Start to download (binance) history " + candle_interval + " ...")
        client = Client(self.__api_key, self.__api_secret)
        history = client.futures_historical_klines(symbol=self.__symbol,
                                                   interval=candle_interval, start_str=start_time,
                                                   end_str=end_time)
        print("History (binance) " + candle_interval + " downloaded.")
        # todo (1) if end_time = none?
        # if not verify_history(history, candle_interval, start_time, end_time):
        #     raise Exception("Invalid downloaded history.")
        return history

