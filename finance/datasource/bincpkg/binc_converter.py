from finance.datasource.converter import MarketDataConverter


class BinanceDataConverter(MarketDataConverter):

    @staticmethod
    def down_hist_to_candle_object_hist(down_hist, candle_interval):
        """
        :param list[list[str]] down_hist:
        :param str candle_interval:
        :return:
        :rtype: list[finance.models.candles.Candle]
        """
        candle_model = MarketDataConverter.get_candle_model(candle_interval)

        candle_object_hist = [candle_model(open=candle_data[1], high=candle_data[2], low=candle_data[3],
                                           close=candle_data[4], volume=candle_data[5], open_time=candle_data[0],
                                           close_time=candle_data[6]) for candle_data in down_hist]

        return candle_object_hist

    # IMPORTANT: single down_candle is not of type df, it is numpy.void, so its better to not be used for now, use down_hist_to_candle_object_hist instead
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
    #     :param list[str] df_candle: [OpenTime, Open, High, Low, Close, Volume, CloseTime, ...]
    #     :param str candle_interval:
    #     :return:
    #     :rtype: finance.models.candles.Candle
    #     """
    #     candle_model = MarketDataConverter.get_candle_model(candle_interval)
    #
    #     candle = candle_model(open=df_candle[1], high=df_candle[2], low=df_candle[3],
    #                           close=df_candle[4], volume=df_candle[5], open_time=df_candle[0],
    #                           close_time=df_candle[6])
    #     return candle

    @staticmethod
    def df_hist_to_candle_object_hist(df_hist, candle_interval):
        """
        :param pandas.DataFrame df_hist:
        :param str candle_interval:
        :return:
        :rtype: list[finance.models.candles.Candle]
        """
        np_hist = df_hist.to_numpy()

        candle_model = MarketDataConverter.get_candle_model(candle_interval)

        candle_object_hist = [candle_model(open=candle_data[1], high=candle_data[2], low=candle_data[3],
                                           close=candle_data[4], volume=candle_data[5], open_time=candle_data[0],
                                           close_time=candle_data[6]) for candle_data in np_hist]

        return candle_object_hist

    @staticmethod
    def df_hist_to_socket_candle_hist(df_hist):
        # todo (0) (binance) first be sure that order of fields in candle from binance socket is the same as the candle in data_frame, then complete this section as in frx_converter
        """
        Converting a DataFrame of candles to list of candles sent by market socket
        :param pandas.DataFrame df_hist:
        :return: list of JSON
        :rtype: list[str]
        """
        np_hist = df_hist.to_numpy()
        socket_candle_hist = []
        # for candle_data in np_hist:  it is for forex
        #     socket_candle = f"{{\"OpenTime\":{candle_data[0]}, \"Open\":{candle_data[1]}, \"High\":{candle_data[2]}, \"Low\":{candle_data[3]}, " \
        #                  f"\"Close\":{candle_data[4]}, \"TickVolume\":{candle_data[5]}, \"Spread\":{candle_data[6]}, \"RealVolume\":{candle_data[7]}}}"
        #     socket_candle_hist.append(socket_candle)
        return socket_candle_hist

    @staticmethod
    def socket_candle_to_candle_object(socket_candle, candle_interval):
        """
        Converting candle coming from web socket to candle object
        :param str socket_candle: JSON
        :param str candle_interval:
        :return:
        :rtype: finance.models.candles.Candle
        """
        pass  # todo (0) (binance) do it
