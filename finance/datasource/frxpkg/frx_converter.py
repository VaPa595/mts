from finance.datasource.converter import MarketDataConverter
from finance.utilities.ufinance import common


class ForexDataConverter(MarketDataConverter):

    @staticmethod
    def down_hist_to_candle_object_hist(down_hist, candle_interval):
        """
        :param numpy.ndarray down_hist:
        :param str candle_interval:
        :return:
        :rtype: list[finance.models.candles.Candle]
        """
        # NOTE:
        # Downloaded hist doesn't contain CloseTime, so it should be created based on OpenTime
        # Also, OpenTime in downloaded hist is in second, which should be converted to millisecond (same as for CloseTime)
        candle_model = MarketDataConverter.get_candle_model(candle_interval)

        candle_object_hist = [candle_model(open=candle_data[1], high=candle_data[2], low=candle_data[3],
                                           close=candle_data[4], volume=candle_data[7], open_time=int(candle_data[0])*1000,
                                           close_time=common.calculate_candle_close_time(candle_interval,
                                                                                         int(candle_data[0])*1000)) for
                              candle_data in down_hist]

        return candle_object_hist

    # IMPORTANT: single down_candle is not of type df, it is Series, so its better to not be used for now, use down_hist_to_candle_object_hist instead
    # @staticmethod
    # def down_candle_to_candle_object_hist(down_candle, candle_interval):
    #     """
    #     :param down_candle:
    #     :param str candle_interval:
    #     :return:
    #     :rtype: finance.models.candles.Candle
    #     """
    #     pass

    # IMPORTANT: single df_candle is not of type df, it is Series, so its better to not be used for now, use df_hist_to_candle_object_hist instead
    # so the code may be wrong (i.e. df_candle[1] is not correct)
    # @staticmethod
    # def df_candle_to_candle_object(df_candle, candle_interval):
    #     """
    #     :param df_candle: [old_todo(0)]
    #     :param str candle_interval:
    #     :return:
    #     :rtype: finance.models.candles.Candle
    #     """
    #     # df_candle: OpenTime, Open, High, Low, Close, tick_volume, spread, real_volume ( no close time)
    #     candle_model = MarketDataConverter.get_candle_model(candle_interval)
    #
    #     candle = candle_model(open=df_candle[1], high=df_candle[2], low=df_candle[3],
    #                           close=df_candle[4], volume=df_candle[7], open_time=df_candle[0],
    #                           close_time=common.calculate_candle_close_time(candle_interval, int(df_candle[0])))
    #     return candle

    @staticmethod
    def df_hist_to_candle_object_hist(df_hist, candle_interval):
        """
        :param pandas.DataFrame df_hist:
        :param str candle_interval:
        :return:
        :rtype: list[finance.models.candles.Candle]
        """
        # NOTE:
        # DF hist doesn't contain CloseTime, so it should be created based on OpenTime
        # Also, OpenTime in DF is in second, which should be converted to millisecond (same as for CloseTime)
        np_hist = df_hist.to_numpy()
        candle_model = MarketDataConverter.get_candle_model(candle_interval)

        candle_object_hist = [candle_model(open=candle_data[1], high=candle_data[2], low=candle_data[3],
                                           close=candle_data[4], volume=candle_data[7], open_time=int(candle_data[0])*1000,
                                           close_time=common.calculate_candle_close_time(candle_interval,
                                                                                         int(candle_data[0])*1000)) for
                              candle_data in np_hist]

        return candle_object_hist

    @staticmethod
    def df_hist_to_socket_candle_hist(df_hist):
        """
        Converting a DataFrame of candles to list of candles sent by market socket
        :param pandas.DataFrame df_hist:
        :return: list of JSON
        :rtype: list[str]
        """
        # NOTE:
        # for forex, the order of fields in data_frame is the same as in candle from market
        # socket sample: {"OpenTime":1675606020.000000, "Open":23367, "High":23373.6, "Low":23367, "Close":23372.1, "TickVolume":482, "Spread":1, "RealVolume":0}
        # OpenTime is in second in original socket data. So, here it should be in second too.
        # OpenTime in DF is also in second. So, no need to any conversion here.

        np_hist = df_hist.to_numpy()
        socket_candle_hist = []

        for candle_data in np_hist:
            socket_candle = f"{{\"OpenTime\":{candle_data[0]}, \"Open\":{candle_data[1]}, \"High\":{candle_data[2]}, \"Low\":{candle_data[3]}, " \
                            f"\"Close\":{candle_data[4]}, \"TickVolume\":{candle_data[5]}, \"Spread\":{candle_data[6]}, \"RealVolume\":{candle_data[7]}}}"
            socket_candle_hist.append(socket_candle)
        return socket_candle_hist

    @staticmethod
    def socket_candle_to_candle_object(socket_candle, candle_interval):
        """
        Converting candle coming from web socket to candle object
        Socket data returned by rcwebsocket.py (used by both forex and binance) is of type dict (in rcwebsocket json.loads() is done)
        Also, OpenTime in socket data is in second, it should be converted to millisecond.
        :param dict socket_candle:
        :param str candle_interval:
        :return:
        :rtype: finance.models.candles.Candle
        """
        candle_model = MarketDataConverter.get_candle_model(candle_interval)
        # json_candle = json.loads(socket_candle)  # socket_candle is of type dict not str (json)
        candle_obj = candle_model(open=socket_candle['Open'], high=socket_candle['High'], low=socket_candle['Low'],
                                  close=socket_candle['Close'], volume=socket_candle['TickVolume'], open_time=int(socket_candle['OpenTime'])*1000,
                                  close_time=common.calculate_candle_close_time(candle_interval, int(socket_candle['OpenTime'])*1000))
        return candle_obj
