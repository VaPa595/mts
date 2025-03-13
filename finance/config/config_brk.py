import configparser
import json
import os

from binance.enums import KLINE_INTERVAL_4HOUR, KLINE_INTERVAL_15MINUTE, KLINE_INTERVAL_1HOUR

from finance.analysis.trendlines.ema import EmaConfig
from finance.analysis.trendlines.trendlinebreak import StaticLineConfig, LineBreakConfig
from finance.decisioncenter.decision_maker_brk import BuyOpeningConfig, BuyClosingConfig, SellClosingConfig, \
    TradeDecisionGeneralConfig, \
    SellOpeningConfig
from finance.market.market import MarketConfig
from finance.market.trade_state_brk import TradeConfig
from finance.utilities import utime
from finance.utilities.uio import uio


class MPQueueConfig:
    def __init__(self, timeout):
        self.timeout = timeout


class BaleBotConfig:
    def __init__(self, token, base_url, decision_chat_id, break_chat_id, ema_chat_id, trade_chat_id):
        self.token = token
        self.base_url = base_url
        self.decision_chat_id = decision_chat_id
        self.break_chat_id = break_chat_id
        self.ema_chat_id = ema_chat_id
        self.trade_chat_id = trade_chat_id


class ConfigReader:
    # todo (3): change to class methods (first think of the situation in which config would be changed at runtime)
    def __init__(self, file_name):
        self.__all_configs = self.__read_config_file(file_name)
        self.__shared_section = self.__read_section('shared')  # todo (3): rename, it is shared with matlab
        self.__slines_section = self.__read_section('sline')
        self.__breaking_section = self.__read_section('breaking')
        self.__ema_section = self.__read_section('ema')
        self.__buy_opening_section = self.__read_section('buy_opening_conditions')
        self.__sell_opening_section = self.__read_section('sell_opening_conditions')
        self.__buy_closing_section = self.__read_section('buy_closing_conditions')
        self.__sell_closing_section = self.__read_section('sell_closing_conditions')
        self.__trade_decision_section = self.__read_section('trade_decision')  # todo (2) rename
        self.__mpqueue_section = self.__read_section('mpqueue')
        self.__bale_bot_section = self.__read_section('bale_bot')
        self.__market_section = self.__read_section('market')
        self.__log_section = self.__read_section('log')
        self.__data_provider_section = self.__read_section('data_provider')
        self.__trade_section = self.__read_section('trade')  # pure trade related

        # self.__static_res_sup_mixed = self.__trend_config.getboolean("static_res_sup_mixed")  # todo (4) what is this?
        self.__static_4h_s_on_1m = self.__slines_section.getboolean("static_lines_4h_s_on_1m")
        self.__static_4h_on_1m = self.__slines_section.getboolean("static_lines_4h_on_1m")
        self.__static_1h_on_1m = self.__slines_section.getboolean("static_lines_1h_on_1m")
        self.__static_15m_on_1m = self.__slines_section.getboolean("static_lines_15m_on_1m")

        self.__sim_server_section = self.__read_section('sim_server')

    @staticmethod
    def __read_config_file(file_name):
        config = configparser.ConfigParser()
        config.read(uio.get_config_file(file_name))
        return config

    def __read_section(self, section_name):
        if section_name not in self.__all_configs:
            raise Exception(f"Invalid config file: No [{section_name}] section")
        else:
            return self.__all_configs[section_name]

    # --------------------------------------------------------------------------

    def __get_sline_conf(self, sline_name):  # todo (1) data_frame is not related to hist_conf
        tolerance = self.__slines_section.getint("tolerance_" + sline_name)
        density = self.__slines_section.getint("dens_" + sline_name)
        # todo (2) convert to datetime if it is possible to convert hist index (now for open column) to datetime
        static_start_day = self.__slines_section.get("static_start_time_" + sline_name)
        static_end_day = self.__slines_section.get("static_end_time_" + sline_name)
        return tolerance, density, static_start_day, static_end_day

    def get_slines_configs(self):
        """
        :return:
        :rtype: list[StaticLineConfig]
        """
        time_format = self.__get_time_format()
        slines_config = []
        if self.__static_4h_on_1m:
            static_tolerance, static_density, static_start_time, static_end_time = self.__get_sline_conf("4h")

            static_start_time_epoch = utime.utc_datetime_to_epoch(static_start_time, time_format)
            static_end_time_epoch = utime.utc_datetime_to_epoch(static_end_time, time_format)

            tc = StaticLineConfig("4h", KLINE_INTERVAL_4HOUR, static_tolerance, static_density,
                                  static_start_time_epoch, static_end_time_epoch)
            slines_config.append(tc)

        if self.__static_4h_s_on_1m:
            static_tolerance, static_density, static_start_time, static_end_time = self.__get_sline_conf("4h_s")

            static_start_time_epoch = utime.utc_datetime_to_epoch(static_start_time, time_format)
            static_end_time_epoch = utime.utc_datetime_to_epoch(static_end_time, time_format)

            tc = StaticLineConfig("4h_s", KLINE_INTERVAL_4HOUR, static_tolerance, static_density,
                                  static_start_time_epoch, static_end_time_epoch)
            slines_config.append(tc)

        if self.__static_1h_on_1m:
            static_tolerance, static_density, static_start_time, static_end_time = self.__get_sline_conf("1h")

            static_start_time_epoch = utime.utc_datetime_to_epoch(static_start_time, time_format)
            static_end_time_epoch = utime.utc_datetime_to_epoch(static_end_time, time_format)

            tc = StaticLineConfig("1h", KLINE_INTERVAL_1HOUR, static_tolerance, static_density,
                                  static_start_time_epoch, static_end_time_epoch)

            slines_config.append(tc)
        if self.__static_15m_on_1m:
            static_tolerance, static_density, static_start_time, static_end_time = self.__get_sline_conf("15m")

            static_start_time_epoch = utime.utc_datetime_to_epoch(static_start_time, time_format)
            static_end_time_epoch = utime.utc_datetime_to_epoch(static_end_time, time_format)

            tc = StaticLineConfig("15m", KLINE_INTERVAL_15MINUTE, static_tolerance, static_density,
                                  static_start_time_epoch, static_end_time_epoch)

            slines_config.append(tc)

        return slines_config

    def __get_time_format(self):
        return self.__slines_section.get("time_format")

    def get_lines_dir(self):
        return self.__shared_section.get("static_lines_dir")

    def get_hist_file(self, candle_interval):
        hist_folder = self.__shared_section.get("hist_folder")
        hist_file = os.path.join(hist_folder, self.__shared_section.get(f"hist_{candle_interval}_file"))
        return hist_file

    def get_breaking_configs(self):  # todo (3): do the same for sline configs
        configs_IDs = json.loads(self.__breaking_section.get("configs_IDs"))
        breaking_configs = []
        for config_id in configs_IDs:
            breaking_configs.append(self.__create_breaking_config_obj(config_id))
        return breaking_configs

    def __create_breaking_config_obj(self, config_id):
        name = self.__breaking_section.get("name_" + config_id)
        candle_interval = self.__breaking_section.get("candle_interval_" + config_id)
        sline_name = self.__breaking_section.get("sline_name_" + config_id)
        breaking_threshold = self.__breaking_section.getfloat("breaking_threshold_" + config_id)
        ema_name = self.__breaking_section.get("ema_name_" + config_id)
        return LineBreakConfig(name=name, candle_interval=candle_interval, sline_name=sline_name,
                               breaking_threshold=breaking_threshold, ema_name=ema_name)

    def get_ema_configs(self):
        configs_IDs = json.loads(self.__ema_section.get("configs_IDs"))
        ema_configs = []
        for config_id in configs_IDs:
            ema_configs.append(self.__create_ema_config_obj(config_id))
        return ema_configs

    def __create_ema_config_obj(self, config_id):
        name = self.__ema_section.get("name_" + config_id)
        span = self.__ema_section.getint("span_" + config_id)
        field = self.__ema_section.get("field_" + config_id)
        dir_interval = self.__ema_section.getint("dir_interval_" + config_id)
        return EmaConfig(name=name, span=span, field=field, dir_interval=dir_interval)

    def get_buy_opening_config(self):
        check_green_candle = self.__buy_opening_section.getboolean("check_green_candle")
        check_ema45_ema825_min_dif = self.__buy_opening_section.getboolean("check_ema45_ema825_min_dif")
        check_ema45_ema825_max_dif = self.__buy_opening_section.getboolean("check_ema45_ema825_max_dif")
        check_closeness_ema45_ema135 = self.__buy_opening_section.getboolean("check_closeness_ema45_ema135")
        check_closeness_ema45_ema100 = self.__buy_opening_section.getboolean("check_closeness_ema45_ema100")
        check_closeness_ema45_ema300 = self.__buy_opening_section.getboolean("check_closeness_ema45_ema300")
        check_closeness_ema45_ema275 = self.__buy_opening_section.getboolean("check_closeness_ema45_ema275")
        ema45_ema825_min_dif = self.__buy_opening_section.getint("ema45_ema825_min_dif")
        ema45_ema135_cls = self.__buy_opening_section.getint("ema45_ema135_cls")
        ema45_ema100_cls = self.__buy_opening_section.getint("ema45_ema100_cls")
        ema45_ema300_cls = self.__buy_opening_section.getint("ema45_ema300_cls")
        ema45_ema275_cls = self.__buy_opening_section.getint("ema45_ema275_cls")

        return BuyOpeningConfig(check_green_candle, check_ema45_ema825_min_dif, check_ema45_ema825_max_dif,
                                check_closeness_ema45_ema135, check_closeness_ema45_ema100,
                                check_closeness_ema45_ema300, check_closeness_ema45_ema275,
                                ema45_ema825_min_dif, ema45_ema135_cls, ema45_ema100_cls, ema45_ema300_cls,
                                ema45_ema275_cls)

    def get_sell_opening_config(self):
        check_red_candle = self.__sell_opening_section.getboolean("check_red_candle")
        check_ema825_ema45_min_dif = self.__sell_opening_section.getboolean("check_ema825_ema45_min_dif")
        check_ema825_ema45_max_dif = self.__sell_opening_section.getboolean("check_ema825_ema45_max_dif")
        check_closeness_ema45_ema135 = self.__sell_opening_section.getboolean("check_closeness_ema45_ema135")
        check_closeness_ema45_ema100 = self.__sell_opening_section.getboolean("check_closeness_ema45_ema100")
        check_closeness_ema45_ema300 = self.__sell_opening_section.getboolean("check_closeness_ema45_ema300")
        check_closeness_ema45_ema275 = self.__sell_opening_section.getboolean("check_closeness_ema45_ema275")
        check_ema_closeness_to_next_sline = self.__sell_opening_section.getboolean("check_ema_closeness_to_next_sline")
        check_price_is_less_than_ema_for_a_while = \
            self.__sell_opening_section.getboolean("check_price_is_less_than_ema_for_a_while")
        ema825_ema45_min_dif = self.__sell_opening_section.getint("ema825_ema45_min_dif")
        ema825_ema45_max_dif = self.__sell_opening_section.getint("ema825_ema45_max_dif")
        ema45_ema135_cls = self.__sell_opening_section.getint("ema45_ema135_cls")
        ema45_ema100_cls = self.__sell_opening_section.getint("ema45_ema100_cls")
        ema45_ema300_cls = self.__sell_opening_section.getint("ema45_ema300_cls")
        ema45_ema275_cls = self.__sell_opening_section.getint("ema45_ema275_cls")
        ema_compare_to_sline_name = self.__sell_opening_section.get("ema_compare_to_sline_name")
        ema_closeness_to_next_sline = self.__sell_opening_section.getint("ema_closeness_to_next_sline")
        ema_compare_to_price_name = self.__sell_opening_section.get("ema_compare_to_price_name")
        ema_compare_to_price_interval = self.__sell_opening_section.getint("ema_compare_to_price_interval")

        return SellOpeningConfig(check_red_candle, check_ema825_ema45_min_dif, check_ema825_ema45_max_dif,
                                 check_closeness_ema45_ema135, check_closeness_ema45_ema100,
                                 check_closeness_ema45_ema300, check_closeness_ema45_ema275,
                                 check_ema_closeness_to_next_sline, check_price_is_less_than_ema_for_a_while,
                                 ema825_ema45_min_dif, ema825_ema45_max_dif, ema45_ema135_cls, ema45_ema100_cls,
                                 ema45_ema300_cls, ema45_ema275_cls, ema_compare_to_sline_name,
                                 ema_closeness_to_next_sline, ema_compare_to_price_name, ema_compare_to_price_interval)

    def get_buy_closing_config(self):
        check_max_loss_after_touching_profit_ceiling = \
            self.__buy_closing_section.getboolean("check_max_loss_after_touching_profit_ceiling")
        check_ema_45_touching_275_after_touching_profit_ceiling = \
            self.__buy_closing_section.getboolean("check_ema_45_touching_275_after_touching_profit_ceiling")
        check_ema_45_touching_100_before_touching_profit_ceiling = \
            self.__buy_closing_section.getboolean("check_ema_45_touching_100_before_touching_profit_ceiling")
        check_first_profit_after_deadline = self.__buy_closing_section.getboolean("check_first_profit_after_deadline")
        check_touching_adaptive_stop_limit = self.__buy_closing_section.getboolean("check_touching_adaptive_stop_limit")
        check_touching_hard_stop_limit = self.__buy_closing_section.getboolean("check_touching_hard_stop_limit")
        return BuyClosingConfig(check_max_loss_after_touching_profit_ceiling,
                                check_ema_45_touching_275_after_touching_profit_ceiling,
                                check_ema_45_touching_100_before_touching_profit_ceiling,
                                check_first_profit_after_deadline, check_touching_adaptive_stop_limit,
                                check_touching_hard_stop_limit)

    def get_sell_closing_config(self):
        check_max_loss_after_touching_profit_ceiling = \
            self.__sell_closing_section.getboolean("check_max_loss_after_touching_profit_ceiling")
        check_ema_45_touching_275_after_touching_profit_ceiling = \
            self.__sell_closing_section.getboolean("check_ema_45_touching_275_after_touching_profit_ceiling")
        check_ema_45_touching_100_before_touching_profit_ceiling = \
            self.__sell_closing_section.getboolean("check_ema_45_touching_100_before_touching_profit_ceiling")
        check_first_profit_after_deadline = self.__sell_closing_section.getboolean("check_first_profit_after_deadline")
        check_touching_adaptive_stop_limit = \
            self.__sell_closing_section.getboolean("check_touching_adaptive_stop_limit")
        check_touching_hard_stop_limit = self.__sell_closing_section.getboolean("check_touching_hard_stop_limit")
        return SellClosingConfig(check_max_loss_after_touching_profit_ceiling,
                                 check_ema_45_touching_275_after_touching_profit_ceiling,
                                 check_ema_45_touching_100_before_touching_profit_ceiling,
                                 check_first_profit_after_deadline, check_touching_adaptive_stop_limit,
                                 check_touching_hard_stop_limit)

    def get_trade_decision_general_config(self):  # todo (3): do the same for sline configs
        pause_on_close = self.__trade_decision_section.getint("open_decision_pause_on_close")
        pause_on_heavy_price = self.__trade_decision_section.getint("open_decision_pause_on_heavy_price")
        pause_on_brk = self.__trade_decision_section.getint("open_decision_pause_on_break")
        active_brk_name = self.__trade_decision_section.get("active_break_config_name")
        auto_market_dir = self.__trade_decision_section.getboolean("auto_market_dir_detection")
        heavy_increase = self.__trade_decision_section.getint("heavy_price_increase")
        heavy_drop = self.__trade_decision_section.getint("heavy_price_drop")
        heavy_interval = self.__trade_decision_section.getint("heavy_price_interval")

        return TradeDecisionGeneralConfig(pause_on_close, pause_on_heavy_price, pause_on_brk, active_brk_name,
                                          auto_market_dir, heavy_increase, heavy_drop, heavy_interval)

    def get_mpqueue_config(self):
        timeout = self.__mpqueue_section.getfloat("timeout")
        return MPQueueConfig(timeout)

    def get_bale_bot_config(self):
        token = self.__bale_bot_section.get("token")
        base_url = self.__bale_bot_section.get("base_url")
        decision_chat_id = self.__bale_bot_section.getint("decision_chat_id")
        break_chat_id = self.__bale_bot_section.getint("break_chat_id")
        ema_chat_id = self.__bale_bot_section.getint("ema_chat_id")
        trade_chat_id = self.__bale_bot_section.getint("trade_chat_id")
        return BaleBotConfig(token, base_url, decision_chat_id, break_chat_id, ema_chat_id, trade_chat_id)

    def get_market_config(self):
        api_key = self.__market_section.get("api_key")
        api_secret = self.__market_section.get("api_secret")
        return MarketConfig(api_key, api_secret)

    def get_trade_config(self):
        hard_stop_limit = self.__trade_section.getfloat("hard_stop_limit")
        profit_ceiling = self.__trade_section.getfloat("profit_ceiling")
        min_profit = self.__trade_section.getfloat("min_profit")
        min_profit_deadline = self.__trade_section.getint("min_profit_deadline")
        max_loss_after_touching_profit_ceiling = self.__trade_section.getfloat("max_loss_after_touching_profit_ceiling")
        adaptive_stop_limit_rate = self.__trade_section.getfloat("adaptive_stop_limit_rate")
        return TradeConfig(hard_stop_limit, profit_ceiling, min_profit, min_profit_deadline,
                           max_loss_after_touching_profit_ceiling, adaptive_stop_limit_rate)

    def get_data_provider_log_file(self):
        return self.__log_section.get("data_provider_log_file")

    def get_trend_log_file(self):
        return self.__log_section.get("trend_log_file")

    def get_trade_log_file(self):
        return self.__log_section.get("trade_log_file")

    def get_hist_1m_days(self):
        return self.__data_provider_section.getint("hist_1m_days")

    def get_large_hist_days(self):
        return self.__data_provider_section.getint("big_hist_days")

    def get_candle_intervals(self):  # todo: use __data_provider_section
        return [KLINE_INTERVAL_15MINUTE, KLINE_INTERVAL_1HOUR, KLINE_INTERVAL_4HOUR]

    def get_wss_host(self):  # web socket server host (for sim_server)
        return self.__sim_server_section.get("host")

    def get_wss_port(self):  # web socket server port (for sim_server)
        return self.__sim_server_section.getint("port")