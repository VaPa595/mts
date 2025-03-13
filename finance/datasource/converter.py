from abc import ABC, abstractmethod

from finance.utilities.ufinance.common import get_candle_model


class MarketDataConverter(ABC):

    @staticmethod
    @abstractmethod
    def down_hist_to_candle_object_hist(down_hist, candle_interval):
        """
        :param down_hist: todo (1): various markets have different return types
        :param str candle_interval:
        :return:
        :rtype: list[finance.models.candles.Candle]
        """
        pass

    # IMPORTANT: we don't use down_candle_to_candle_object_hist and df_candle_to_candle_object anymore, because types of single down_candle or df_candle are not favorable

    # @staticmethod
    # @abstractmethod
    # def down_candle_to_candle_object_hist(down_candle, candle_interval):
    #     """
    #     :param down_candle: old_todo (1): various markets have different return types
    #     :param str candle_interval:
    #     :return:
    #     :rtype: finance.models.candles.Candle
    #     """
    #     pass
    #
    # @staticmethod
    # @abstractmethod
    # def df_candle_to_candle_object(df_candle, candle_interval):
    #     """
    #     :param list[str] df_candle: [OpenTime, Open, High, Low, Close, Volume, CloseTime, ...]  # old_todo(00)
    #     :param str candle_interval:
    #     :return:
    #     :rtype: finance.models.candles.Candle
    #     """
    #     pass

    @staticmethod
    @abstractmethod
    def df_hist_to_candle_object_hist(df_hist, candle_interval):
        """
        :param pandas.DataFrame df_hist:
        :param str candle_interval:
        :return:
        :rtype: list[finance.models.candles.Candle]
        """
        pass

    @staticmethod
    def get_candle_model(candle_interval):  # todo(2): if model is changed from mongoengine...
        """
        :param str candle_interval:
        :return:
        :rtype: mongoengine.base.metaclasses.TopLevelDocumentMetaclass
        """
        return get_candle_model(candle_interval)

    @staticmethod
    @abstractmethod
    def df_hist_to_socket_candle_hist(df_hist):
        """
        Converting a DataFrame of candles to list of candles sent by market socket
        :param pandas.DataFrame df_hist:
        :return: list of JSON
        :rtype: list[str]
        """
        pass

    @staticmethod
    @abstractmethod
    def socket_candle_to_candle_object(socket_candle, candle_interval):
        """
        Converting candle coming from web socket to candle object
        :param str socket_candle: JSON
        :param str candle_interval:
        :return:
        :rtype: finance.models.candles.Candle
        """
        pass

