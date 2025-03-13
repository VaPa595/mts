from finance.utilities import umath
from finance.utilities.ufinance import common


def find_initial_next_lines_to_be_broken(hist_1m, hist_1m_df, candle_interval, slines, breaking_threshold):
    """
    starting from end of hist_1m returns next up/downward lines to be broken on the last seen line break
    :param deque[Candle] hist_1m:
    :param pd.DataFrame hist_1m_df:
    :param str candle_interval:
    :param list[float] slines:
    :param float breaking_threshold:
    :return:
    :rtype: (float, float)
    """
    hist = common.get_all_candles_from_hist_1m(hist_1m, candle_interval)

    for candle in hist[::-1]:
        ema_275_dir = common.get_ema_dir_on_df_hist(df_hist=hist_1m_df.loc[:candle.close_time], field='close', span=275,
                                                    dir_interval=5)
        next_upward_line_to_be_broken, next_downward_line_to_be_broken = \
            find_initial_next_lines_to_be_broken_if_candle_is_broken_some_lines(candle, ema_275_dir, slines,
                                                                                breaking_threshold)
        if next_upward_line_to_be_broken > -1:  # both are -1 or both are not. This candle has broken some lines
            return next_upward_line_to_be_broken, next_downward_line_to_be_broken
    return -1, -1  # no candle with green/red color is found while ema dir at the end of candle were 1/-1


def find_initial_next_lines_to_be_broken_if_candle_is_broken_some_lines(candle, ema_dir, slines,
                                                                        breaking_threshold):
    """
    :param Candle candle:
    :param float ema_dir:
    :param list[float] slines:
    :param float breaking_threshold:
    :return:
    :rtype: (float, float)
    """
    # In the case of ema_dir is opposite of candle color:
    next_upward_line_to_be_broken = -1
    next_downward_line_to_be_broken = -1

    break_dir = 0
    candle_color = common.find_candle_color(candle)

    if ema_dir == 1 and candle_color == 1:  # raising and green
        next_upward_line_to_be_broken = 100000000  # in the case of no next upward line is found.  # todo 2: from config
        next_downward_line_to_be_broken = 0  # in the case of no next downward line is found.  # todo 2: from config
        for sline in slines:
            if common.candle_broke_sline(candle, sline, breaking_threshold):  # it is definitely an upward break
                break_dir = 1
                next_downward_line_to_be_broken = sline
            elif break_dir == 1:  # previous line is broken but not this one
                next_upward_line_to_be_broken = sline
                break
            else:  # this is the first line and is not broken
                next_upward_line_to_be_broken = sline
                break
    elif ema_dir == -1 and candle_color == -1:  # falling and red
        next_upward_line_to_be_broken = 100000000  # in the case of no next upward line is found.
        next_downward_line_to_be_broken = 0  # in the case of no next downward line is found.
        for sline in slines[::-1]:
            if common.candle_broke_sline(candle, sline, breaking_threshold):  # it is definitely a downward break:
                break_dir = -1
                next_upward_line_to_be_broken = sline
            elif break_dir == -1:  # previous line is broken but not this one
                next_downward_line_to_be_broken = sline
                break
            else:  # this is the first line and is not broken
                next_downward_line_to_be_broken = sline
                break

    return next_upward_line_to_be_broken, next_downward_line_to_be_broken


def find_next_line_to_be_broken(broken_line, slines, breaking_dir):
    if breaking_dir == 1:  # upward
        next_line = 100000
        for sline in slines:
            if umath.is_greater(sline, broken_line):
                next_line = sline
                break
    else:  # downward
        next_line = 0
        for sline in slines[::-1]:
            if umath.is_less(sline, broken_line):
                next_line = sline
                break
    return next_line


class LineBreakingStatus:
    def __init__(self, breaking_name, candle_interval):
        self.breaking_name = breaking_name
        self.candle_interval = candle_interval  # todo (3) not used
        self.breaking_threshold = 0.6  # todo (2): get form config

        self.broken_line = 0
        self.breaking_dir = 0
        self.is_new_break = False  # it is new until the next corresponding tick

        # self.is_new_line_breaking = 0  # -1:new downward, 1: new upward, 0: is not new
        self.next_upward_line_to_be_broken = 0
        self.next_downward_line_to_be_broken = 0
        # self.last_upward_broken_line = 0  # May be just for log. It is note used in the logic of the code anymore.
        # self.last_downward_broken_line = 0
        self.upward_broken_count = 0
        self.downward_broken_count = 0

    def verify_change_in_next_lines_to_be_broken(self, slines):
        old_next_upward_line_to_be_broken = self.next_upward_line_to_be_broken
        old_next_downward_line_to_be_broken = self.next_downward_line_to_be_broken

        self.next_upward_line_to_be_broken = 100000  # if no upward line is found
        indeterminate_lines = []  # just for log
        pre_sline_to_old_next_downward = 0
        next_downward_is_updated = 0

        i = 0  # just is needed when len(slines)==0  # to prevent null exception in the next loop on i.
        for i in range(len(slines)):
            sline = slines[i]
            if umath.is_less(sline, old_next_downward_line_to_be_broken):
                pre_sline_to_old_next_downward = sline
            elif umath.are_equal(sline, old_next_downward_line_to_be_broken):
                self.next_downward_line_to_be_broken = sline
                next_downward_is_updated = 1
                i += 1  # to prevent adding next_downward_line_to_be_broken to indeterminate_lines
                break
            elif umath.is_greater(sline, old_next_downward_line_to_be_broken):
                self.next_downward_line_to_be_broken = pre_sline_to_old_next_downward
                # we don't add this sline to indeterminate_lines, but in next loop we continue form hear
                next_downward_is_updated = 1
                break

        if next_downward_is_updated == 0:
            self.next_downward_line_to_be_broken = pre_sline_to_old_next_downward

        for j in range(i, len(slines)):
            sline = slines[j]
            if umath.is_less(sline, old_next_upward_line_to_be_broken):
                indeterminate_lines.append(sline)
            elif umath.are_equal(sline, old_next_upward_line_to_be_broken):
                self.next_upward_line_to_be_broken = sline
                break
            elif umath.is_greater(sline, old_next_upward_line_to_be_broken):
                self.next_upward_line_to_be_broken = sline
                break

    def update_line_break_status(self, candle, ema_dir, slines):  # todo (3): IMP: separate (SRP)
        """
        It also considers new lines between old next up/downward lines to be broken
        :param Candle candle:
        :param int ema_dir:
        :param list[float] slines:
        """

        self.update_broken_line_and_dir(candle, ema_dir, slines)
        if self.breaking_dir == 1:
            # print(f"Upward-break: Sline {self.broken_line} --- Time: {candle.open_time}")
            print(f"U_{self.broken_line} --- CloseTime: {candle.close_time}")
            # print("U")
        elif self.breaking_dir == -1:
            # print(f"Downward-break: Sline {self.broken_line} --- Time: {candle.open_time}")
            print(f"D_{self.broken_line} --- CloseTime: {candle.close_time}")
            # print("D")

        self.update_next_lines_to_be_broken(slines)  # todo (1) if new broken? (if dir!=0 it is new)
        # self.__upward_broken_count = 0
        # self.__downward_broken_count = 0

    def update_broken_line_and_dir(self, candle, ema_dir, slines):  # todo (3) use required values of lbk_status
        """
        It also considers new lines between old next up/downward lines to be broken
        :param Candle candle:
        :param int ema_dir:
        :param list[float] slines:
        """
        self.broken_line = 0
        self.breaking_dir = 0
        self.is_new_break = False
        candle_color = common.find_candle_color(candle)
        if ema_dir == 1 and candle_color == 1:  # raising and green
            for sline in slines:  # to find the highest broken line
                # to consider new slines between old next ...
                if umath.is_greater(sline, self.next_downward_line_to_be_broken):
                    if common.candle_broke_sline(candle, sline, self.breaking_threshold):
                        self.broken_line = sline
                        self.breaking_dir = 1
                        self.is_new_break = True
        elif ema_dir == -1 and candle_color == -1:  # falling and red
            for sline in slines[::-1]:  # to find the lowest broken line
                if umath.is_less(sline, self.next_upward_line_to_be_broken):  # to consider new slines between old next
                    if common.candle_broke_sline(candle, sline, self.breaking_threshold):
                        self.broken_line = sline
                        self.breaking_dir = -1
                        self.is_new_break = True

    def update_next_lines_to_be_broken(self, slines):  # todo (3) use required values of lbk_status

        if self.breaking_dir == 1:  # expected line (or higher) is broken( not repetitive) and rising
            self.next_upward_line_to_be_broken = find_next_line_to_be_broken(self.broken_line, slines, 1)
            self.next_downward_line_to_be_broken = self.broken_line  # todo (4) use counter

        elif self.breaking_dir == -1:  # expected line (or lower) is broken(not repetitive) and falling
            self.next_upward_line_to_be_broken = self.broken_line
            self.next_downward_line_to_be_broken = find_next_line_to_be_broken(self.broken_line, slines, -1)

    def __str__(self):
        return f"Name: {self.breaking_name}, IsNewBrk: {self.is_new_break} BrkLine: {self.broken_line}, " \
               f"BrkDir: {self.breaking_dir}, NextUpLine: {self.next_upward_line_to_be_broken}, " \
               f"NextDownLine: {self.next_downward_line_to_be_broken}"


class StaticLineConfig:
    def __init__(self, name, candle_interval, static_tolerance, static_density, start_time, end_time):
        """
        :param str name: name of config (should be unique)
        :param str candle_interval: interval of the candle: i.e. 1m, 15m, 1h, 4h
        :param int static_tolerance: # todo (2) rename
        :param int static_density: # todo (2) rename
        :param int start_time: start time of initial interval in epoch (ms)
        :param int end_time: start time of initial interval in epoch (ms)
        """
        self.name = name
        self.candle_interval = candle_interval
        self.static_tolerance = static_tolerance
        self.static_density = static_density
        self.start_time = start_time
        self.end_time = end_time


class LineBreakConfig:
    def __init__(self, name, candle_interval, sline_name, breaking_threshold, ema_name):
        """
        :param str name: name of config (should be unique)
        :param str candle_interval: interval of the candle: i.e. 1m, 15m, 1h, 4h
        :param str sline_name: name of static line config to be broken
        :param float breaking_threshold:
        :param str ema_name:
        """
        self.name = name
        self.candle_interval = candle_interval
        self.sline_name = sline_name
        self.breaking_threshold = breaking_threshold  # todo (2) it is not used
        self.ema_name = ema_name


