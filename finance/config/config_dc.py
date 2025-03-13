import configparser
import json

from finance.analysis.indicators.atr import AtrConfig
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


class ConfigReader:  # todo (2): define an abstract class and rename this as ConfigReaderDC (likewise for BRK)
    # todo (3): change to class methods (first think of the situation in which config would be changed at runtime)
    def __init__(self, file_name):
        self.__all_configs = self.__read_config_file(file_name)
        self.__general_section = self.__read_section('general')
        self.__hist_files_section = self.__read_section('hist_files')
        self.__data_provider_section = self.__read_section('data_provider')
        self.__atr_section = self.__read_section('atr')
        self.__trade_section = self.__read_section('trade')  # pure trade related
        # self.__trade_decision_section = self.__read_section('trade_decision')  # todo (2) rename
        # self.__market_section = self.__read_section('market')
        self.__mpqueue_section = self.__read_section('mpqueue')
        self.__bale_bot_section = self.__read_section('bale_bot')
        self.__log_section = self.__read_section('log')
        self.__sim_server_section = self.__read_section('sim_server')

    @staticmethod
    def __read_config_file(file_name):
        config = configparser.ConfigParser(interpolation=configparser.ExtendedInterpolation())
        config.read(uio.get_config_file(file_name))
        return config

    def __read_section(self, section_name):
        if section_name not in self.__all_configs:
            raise Exception(f"Invalid config file: No [{section_name}] section")
        else:
            return self.__all_configs[section_name]

    # --------------------------------------------------------------------------
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

    # def get_market_config(self):
    #     api_key = self.__market_section.get("api_key")
    #     api_secret = self.__market_section.get("api_secret")
    #     return MarketConfig(api_key, api_secret)
    #
    # def get_trade_config(self):
    #     hard_stop_limit = self.__trade_section.getfloat("hard_stop_limit")
    #     profit_ceiling = self.__trade_section.getfloat("profit_ceiling")
    #     min_profit = self.__trade_section.getfloat("min_profit")
    #     min_profit_deadline = self.__trade_section.getint("min_profit_deadline")
    #     max_loss_after_touching_profit_ceiling = self.__trade_section.getfloat("max_loss_after_touching_profit_ceiling")
    #     adaptive_stop_limit_rate = self.__trade_section.getfloat("adaptive_stop_limit_rate")
    #     return TradeConfig(hard_stop_limit, profit_ceiling, min_profit, min_profit_deadline,
    #                        max_loss_after_touching_profit_ceiling, adaptive_stop_limit_rate)

    def get_hist_file_1m(self):
        return self.__hist_files_section.get("hist_file_1m")

    def get_hist_file_small(self):
        return self.__hist_files_section.get("hist_file_small")

    def get_hist_file_large(self):
        return self.__hist_files_section.get("hist_file_large")

    def get_data_provider_log_file(self):
        return self.__log_section.get("data_provider_log_file")

    def get_trend_log_file(self):
        return self.__log_section.get("trend_log_file")

    def get_trade_log_file(self):
        return self.__log_section.get("trade_log_file")

    def get_db_log_file(self):
        return self.__log_section.get("db_log_file")

    def get_rwc_log_file(self):
        return self.__log_section.get("rwc_log_file")  # todo (binc): use this log file for binance

    def get_frx_listener_log_file(self):
        return self.__log_section.get("frx_listener_log_file")

    def get_alg_log_file(self):
        return self.__log_section.get("alg_log_file")

    def get_main_log_file(self):
        return self.__log_section.get("main_log_file")

    def get_hist_1m_days(self):
        return self.__data_provider_section.getint("hist_1m_days")

    def get_large_hist_days(self):
        return self.__data_provider_section.getint("big_hist_days")

    def get_current_time(self):
        time_format = self.__general_section.get("time_format")
        curr_time = self.__data_provider_section.get("current_time")
        if curr_time == 'None':
            return None
        return utime.utc_datetime_to_epoch(curr_time, time_format)

    def get_candle_intervals(self):  # todo: use __data_provider_section  (in other config files)
        # aa = self.__data_provider_section.get("candle_intervals")
        return json.loads(self.__data_provider_section.get("candle_intervals"))

    def get_small_interval(self):
        return self.__trade_section.get("small_interval")

    def get_large_interval(self):
        return self.__trade_section.get("large_interval")

    def get_default_volume(self):
        return self.__trade_section.getfloat("default_volume")

    def get_symbol(self):
        return self.__trade_section.get("symbol")

    def get_buy_trade_status(self):
        return self.__trade_section.getboolean("buy_trade")

    def get_sell_trade_status(self):
        return self.__trade_section.getboolean("sell_trade")

    def get_only_open_alert(self):
        return self.__trade_section.getboolean("only_open_alert")

    def get_atr_configs(self):
        time_format = self.__general_section.get("time_format")
        configs_IDs = json.loads(self.__atr_section.get("configs_IDs"))
        atr_configs = []
        for config_id in configs_IDs:
            atr_configs.append(self.__create_atr_config_obj(config_id, time_format))
        return atr_configs

    def get_wss_host(self):  # web socket server host (for sim_server)
        return self.__sim_server_section.get("host")

    def get_wss_port(self):  # web socket server port (for sim_server)
        return self.__sim_server_section.getint("port")

    def __create_atr_config_obj(self, config_id, time_format):
        candle_interval = self.__atr_section.get("candle_interval_" + config_id)

        start_time = self.__atr_section.get("start_time_" + config_id)
        start_time_epoch = utime.utc_datetime_to_epoch(start_time, time_format)

        end_time = self.__atr_section.get("end_time_" + config_id)
        end_time_epoch = None if end_time == 'None' else utime.utc_datetime_to_epoch(end_time, time_format)

        return AtrConfig(candle_interval=candle_interval, start_time=start_time_epoch, end_time=end_time_epoch)


