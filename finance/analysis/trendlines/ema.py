from finance.utilities.ufinance import common
from finance.utilities.utime import TicToc


class EMA:
    """
    :var pd.DataFrame __values:
    :type __values: pd.DataFrame or None
    """

    def __init__(self, name, span, field, dir_interval, hist_df=None):
        """
        :param str name:
        :param int span:
        :param str field:
        :param int dir_interval:
        :param pandas.DataFrame hist_df:
        """
        self.__name = name
        self.__span = span
        self.__field = field
        self.__dir_interval = dir_interval
        self.__values = None
        self.dir = None
        self.__tic_toc = TicToc()
        if hist_df is not None:
            self.update(hist_df)

    def update(self, hist_df):
        # self.__tic_toc.tic()
        # self.__values = common.exp_mov_avg_on_list_hist(hist, self.__field, self.__span)  # todo (2): 275 as config
        self.__values = common.exp_mov_avg_on_df_hist(hist_df, self.__field, self.__span)  # todo (2): 275 as config
        # print(self.__tic_toc.toc())
        self.dir = common.get_ema_dir(self.__values, self.__dir_interval)  # todo (2): 5 as config

    def __len__(self):
        return len(self.__values.index)

    def __getitem__(self, item):
        return self.__values.iloc[item]

    def __str__(self):
        return f"Name: {self.__name}, Span: {self.__span}, Dir: {self.dir}"


class EmaConfig:
    """
    :type name: str
    :type span: int
    :type field: str
    :type dir_interval: int
    """

    def __init__(self, name, span, field, dir_interval):
        self.name = name
        self.span = span
        self.field = field
        self.dir_interval = dir_interval


