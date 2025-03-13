from heapq import merge

import pandas
import trendln

from finance.models.extremum import Extremum
from finance.models.slines import SLine


def average(lst):
    return sum(lst) / len(lst)


def calc_static_slines(points, tolerance, dens):  # todo: IMP-points should be sorted do sorting here
    """
    Points which lie in an interval of length = tolerance are grouped together and a horizontal line is created as
    average of the group, i.e. h = average(group)
    Note: it is necessary that points be sorted
    :param points: set of points (exterma) that we want to create horizontal lines (sline) crossing them
    :type points: list[float]
    :param tolerance: maximum tolerable interval that points in there could be considered as a group to create a line
    :type tolerance: float
    :param dens: minimum number of points in each group to create a line
    :type dens: int
    :return: horizontal lines, each line is represented as a point, i.e. h = average(group).
    :rtype: list[float]
    """
    slines = []
    if len(points) == 0:  # todo (1): make sure such checking is considered elsewhere.
        return slines
    group = []
    min_ = points[0]
    group.append(min_)
    for i in range(1, len(points)):
        if points[i] - min_ <= tolerance:
            group.append(points[i])
        else:
            if len(group) >= dens:
                sline = average(group)
                slines.append(sline)
            group.clear()
            group.append(points[i])
            min_ = points[i]
    if len(group) >= dens:  # last group
        sline = average(group)
        slines.append(sline)

    return slines


def dyn_res_sup_lines(hist):  # not used in the project
    (minimaIdxs, pmin, mintrend, minwindows), (maximaIdxs, pmax, maxtrend, maxwindows) = \
        trendln.calc_support_resistance(hist)
    sup_lines = [[sup_trend[1][0], sup_trend[1][1]] for sup_trend in mintrend]
    res_lines = [[res_trend[1][0], res_trend[1][1]] for res_trend in maxtrend]
    return sup_lines, res_lines


def static_res_sup(points, tolerance, dens):
    """
    First minimum and maximum points (exterma) are found then are sorted then calc_static_slines() is called to create
    slines for each type of exterma. Resilience slines for maximum points and support slines for minimum points.
    :param points: set of points (exterma) that we want to create horizontal lines (sline) crossing them
    :type points: list[float]
    :param tolerance: maximum tolerable interval that points in there could be considered as a group to create a line
    :type tolerance: float
    :param dens: minimum number of points in each group to create a line
    :type dens: int
    :return: It returns support and resilience slines corresponding to minimum and maximum points, respectively.
    :rtype:
    """
    # (minimaIdxs, pmin, mintrend, minwindows), (maximaIdxs, pmax, maxtrend, maxwindows) = \
    #     trendln.calc_support_resistance(hist)
    minima_idxs, maxima_idxs = trendln.get_extrema(points)
    # minima = points[minima_idxs].sort_values(kind='mergesort').__values  # works for DataFrame
    # maxima = points[maxima_idxs].sort_values(kind='mergesort').__values  # works for DataFrame

    minima = [points[i] for i in minima_idxs]
    maxima = [points[i] for i in maxima_idxs]

    exterma_idx = list(merge(minima_idxs, maxima_idxs))
    return calc_static_slines(minima, tolerance, dens), calc_static_slines(maxima, tolerance, dens), exterma_idx


def calc_static_slines_mixed(points, tolerance, dens):
    """
    First minimum and maximum points (exterma) are found then are sorted then calc_static_slines() is called to create
    slines for mixed exterma (minimum and maximum points are seen together)
    :param points: set of points (exterma) that we want to create horizontal lines (sline) crossing them
    :type points: list[float]
    :param tolerance: maximum tolerable interval that points in there could be considered as a group to create a line
    :type tolerance: float
    :param dens: minimum number of points in each group to create a line
    :type dens: int
    :return: horizontal lines, each line is represented as a point, i.e. h = average(group).
    :rtype: list[float]
    """
    minima_idxs, maxima_idxs = trendln.get_extrema(points)

    exterma_idx = list(merge(minima_idxs, maxima_idxs))

    # sorted_exterma = hist[exterma_idx].sort_values(kind='mergesort').values  # works for DataFrame
    exterma = [points[i] for i in exterma_idx]
    exterma.sort()

    return calc_static_slines(exterma, tolerance, dens), exterma


def calc_exterma(points):
    minima_idxs, maxima_idxs = trendln.get_extrema(points)
    minima = [points[i] for i in minima_idxs]
    maxima = [points[i] for i in maxima_idxs]
    return minima, maxima


def calc_exterma_index(points):
    """
    :param points:
    :type points:
    :return:
    :rtype: (list[int], list[int])
    """
    minima_idxs, maxima_idxs = trendln.get_extrema(points)
    return minima_idxs, maxima_idxs


def calc_exterma_index_for_hist(hist):
    """
    :param hist:
    :type hist: pandas.DataFrame
    :return:
    :rtype: (list[int], list[int])
    """
    minima_idxs, maxima_idxs = trendln.get_extrema((hist.Low.values, hist.High.values), extmethod=0,  accuracy=3)
    return minima_idxs, maxima_idxs


def find_extrema_apc2(hist, atr=2360):  # atr = 2360  # 12400  # 5860  # 2360  # 946  #
    """
    :param hist:
    :type hist: list[finance.models.candles.Candle]
    :param atr:
    :type atr: int
    :return:
    :rtype: list[Extremum]
    """
    extrema = []
    last_price_ceiling_time = 0
    last_price_floor_time = 0
    last_price_ceiling = -1
    last_price_floor = 100000000
    wait_for_increase = False
    wait_for_drop = False
    for candle in hist:
        skip = False
        if candle.high > last_price_ceiling:
            last_price_ceiling = candle.high
            # if last_price_ceiling == 40875.0:
            #     print(1)
            last_price_ceiling_time = candle.open_time
            skip = True
        if candle.low < last_price_floor:
            last_price_floor = candle.low
            last_price_floor_time = candle.open_time
            skip = True
        # if one of the following condition is true, current iteration should be ended, thus, we use elif.
        if not wait_for_drop and not wait_for_increase and last_price_ceiling - candle.low >= 3*atr:
            wait_for_increase = True
        elif not wait_for_increase and not wait_for_drop and candle.high - last_price_floor >= 3*atr:
            wait_for_drop = True
        elif not skip and wait_for_increase:
            if candle.high - last_price_floor >= atr:
                extrema.append(Extremum(price=last_price_floor, extype="minimum", interval="4h",
                                        time=last_price_floor_time))
                last_price_ceiling = candle.high
                # last_price_floor = candle.low
                wait_for_increase = False
        elif not skip and wait_for_drop:
            if last_price_ceiling - candle.low >= atr:
                extrema.append(Extremum(price=last_price_ceiling, extype="maximum", interval="4h",
                                        time=last_price_ceiling_time))
                # print(last_price_ceiling)
                # last_price_ceiling = candle.high
                last_price_floor = candle.low
                wait_for_drop = False

    return extrema


def create_slines_from_extrema(extrema):
    """
    each extremum is considered as one sline
    :param extrema: list of extrema
    :type extrema: list[Extremum]
    :return:
    :rtype: list[SLine]
    """
    slines = []
    for extremum in extrema:
        slines.append(SLine(price=extremum.price, extype=extremum.extype, interval=extremum.interval,
                            time=extremum.time, hits=0))
    return slines


class TrendLinesApi:
    @staticmethod
    def get_slines(points, tolerance, density):  # IMP- points are just open, or close, or high, ...
        """
        In this project to create slines, both minimum and maximum points are seen together (mixed), so there is no
        separate resilience or support sline. So, the method calc_static_slines_mixed() is called.
        :param points: set of points (exterma) that we want to create horizontal lines (sline) crossing them
        :type points: list[float]
        :param tolerance: maximum tolerable interval that points in there could be considered as a group to create a line
        :type tolerance: float
        :param density: minimum number of points in each group to create a line
        :type density: int
        :return: horizontal lines, each line is represented as a point, i.e. h = average(group).
        :rtype: list[float]
        """
        try:
            slines, exterma = calc_static_slines_mixed(points, tolerance, density)
            return slines
        except:
            print(f"Exception in calculation of slines, returning [].")
            return []


class SLineInfo:
    def __init__(self, hist_name, slines, start, end):
        """
        :param str hist_name:
        :param list[float] slines:
        :param int start:
        :param int end:
        """
        self.hist_name = hist_name
        self.slines = slines
        self.start = start
        self.end = end


class RuntimeTrendLines:
    # method in case of multi trading
    __all_last_slines_info = {}

    def update_slines_info(self, sline_config, points):
        if len(points) == 0:
            print(f"Empty points for getting trend lines: {sline_config.name}")  # todo, need to log?
        slines = TrendLinesApi.get_slines(points, sline_config.static_tolerance, sline_config.static_density)
        slines_info = SLineInfo(sline_config.name, slines, -1, -1)  # todo (1) set start/end of history
        self.__all_last_slines_info[sline_config.name] = slines_info
        return slines_info

    def get_all_last_slines_info(self):
        return self.__all_last_slines_info

    def get_last_slines_info(self, name):
        """
        :param str name:
        :return:
        :rtype: SLineInfo
        """
        return self.__all_last_slines_info[name]  # todo (3) define type of the value in the dictionary


class BreakInfo:
    def __init__(self, breaking_name, sline_name, candle_interval, candle, ema_dir, slines):
        self.breaking_name = breaking_name
        self.sline_name = sline_name
        self.candle_interval = candle_interval
        self.candle = candle
        self.ema_dir = ema_dir  # in future it is possible to need different ema for each config
        self.slines = slines

