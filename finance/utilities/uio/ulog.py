import logging
import logging.handlers as handlers

from finance.utilities.uio import uio


def get_default_logger(name, filename, level=logging.DEBUG):
    """
    It creates and returns a logger which save the logs in data folder
    :param str name: logger name
    :param str filename: name of the log file
    :param int level: default log level
    :return:
    :rtype: logging.Logger
    """
    print(f"Logger: {name}")
    logger = logging.getLogger(name)
    logger.setLevel(level)  # necessary
    if not logger.handlers:
        # Create handlers
        # f_handler = logging.FileHandler(uio.get_log_file(filename))
        f_handler = handlers.RotatingFileHandler(uio.get_log_file(filename), maxBytes=20*1024*1024, backupCount=10)
        # Create formatters and add it to handlers
        f_format = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s: - %(message)s')
        f_handler.setFormatter(f_format)

        # Add handlers to the logger
        # logger.addHandler(c_handler)
        logger.addHandler(f_handler)

    return logger


# def create_logger(module_name, log_name, level):
#     """
#     :param str module_name: name of caller module
#     :param str log_name:
#     :param int level: CRITICAL=50, FATAL=CRITICAL, ERROR=40, WARNING=30, WARN=WARNING, INFO=20, DEBUG=10,
#                                 NOTSET=0
#     :return:
#     :rtype: RootLogger
#     """
#     # logger = logging.getLogger(__name__) --> Formatter('%(name)s')
#
#     # Calling getLogger() without arguments returns the root logger so when you set the level to logging.DEBUG
#     # you are also setting the level for other modules that use that logger.
#     logger = logging.getLogger(module_name)
#     logger.setLevel(level)
#
#     # Create handlers
#     c_handler = logging.StreamHandler()  # shell or cmd
#     f_handler = logging.FileHandler(uio.get_log_file(log_name))
#     c_handler.setLevel(logging.DEBUG)
#     f_handler.setLevel(logging.DEBUG)
#     # Create formatters and add it to handlers
#     c_format = logging.Formatter('%(asctime)s - %(funcName)s - %(levelname)s - %(message)s')
#     f_format = logging.Formatter('%(asctime)s - %(funcName)s - %(levelname)s - %(message)s')
#     c_handler.setFormatter(c_format)
#     f_handler.setFormatter(f_format)
#     # Add handlers to the logger
#     logger.addHandler(c_handler)
#     logger.addHandler(f_handler)
#     return logger
