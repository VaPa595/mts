import numpy as np
import pandas as pd


def calc_atr(data):
    """
    :param pd.DataFrame data:
    :return:
    :rtype: float
    """
    periods = [264, 132, 66, 21, 10, 5]
    #coefficients = [8, 5, 3, 2, 1, 1]
    coefficients = [3, 3, 3, 3, 3, 3]
    high_low = data['high'] - data['low']
    high_close = np.abs(data['high'] - data['close'].shift())
    low_close = np.abs(data['low'] - data['close'].shift())
    ranges = pd.concat([high_low, high_close, low_close], axis=1)  # todo why not np?

    true_range = np.max(ranges, axis=1)
    atr_sum = 0
    for i in range(len(periods)):
        period = periods[i]
        atr = (sum(true_range[-period:]) / period) * coefficients[i]
        atr_sum += atr

    return atr_sum / sum(coefficients)


class AtrConfig:
    def __init__(self, candle_interval, start_time, end_time=None):
        """
        :param str candle_interval: interval of the candle: i.e. 1m, 15m, 1h, 4h
        :param int start_time: start time of initial interval in epoch (ms)
        :param int or None end_time: start time of initial interval in epoch (ms)
        """
        self.candle_interval = candle_interval
        self.start_time = start_time
        self.end_time = end_time

