import logging
import os
import sys
from typing import Text

from redditrepostsleuth.core.logfilters import SingleLevelFilter

default_format = '%(asctime)s - %(module)s:%(funcName)s:%(lineno)d - [%(process)d][%(threadName)s] - %(levelname)s: %(message)s'
image_search_trace_format = '%(asctime)s - %(module)s:%(funcName)s:%(lineno)d - [Search ID: %(search_id)d] - %(levelname)s: %(message)s'

def get_configured_logger(name: Text = None, format: Text = None) -> logging.Logger:

    log = logging.getLogger(name or __name__)
    log.setLevel(os.getenv('LOG_LEVEL', 'DEBUG'))
    formatter = logging.Formatter(format or default_format)

    general_handler = logging.StreamHandler(sys.stdout)
    general_filter = SingleLevelFilter(logging.INFO, False)
    general_handler.setFormatter(formatter)
    general_handler.addFilter(general_filter)
    log.addHandler(general_handler)

    error_handler = logging.StreamHandler(sys.stderr)
    error_filter = SingleLevelFilter(logging.WARNING)
    error_handler.setFormatter(formatter)
    error_handler.addFilter(error_filter)
    log.addHandler(error_handler)
    log.propagate = False
    return log

def configure_logger(name: Text = None, format: Text = None, filters: list[logging.Filter] = []) -> logging.Logger:
    log = logging.getLogger(name or '')
    log.setLevel(os.getenv('LOG_LEVEL', 'DEBUG'))
    log.handlers = []
    formatter = logging.Formatter(format or default_format)
    general_handler = logging.StreamHandler(sys.stdout)
    general_handler.setFormatter(formatter)
    general_handler.setLevel(os.getenv('LOG_LEVEL', 'DEBUG'))
    error_handler = logging.StreamHandler(sys.stderr)
    error_filter = SingleLevelFilter(logging.WARNING)
    error_handler.setFormatter(formatter)
    for fltr in filters:
        general_handler.addFilter(fltr)
        error_handler.addFilter((fltr))
    general_handler.addFilter(SingleLevelFilter(logging.INFO, False))
    error_handler.addFilter(SingleLevelFilter(logging.WARNING))
    log.addHandler(general_handler)
    log.addHandler(error_handler)
    return log

log = get_configured_logger(__name__)
