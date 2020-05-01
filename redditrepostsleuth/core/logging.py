import logging
import os
import sys

from redditrepostsleuth.core.logfilters import SingleLevelFilter

log = logging.getLogger(__name__)
log.setLevel(os.getenv('LOG_LEVEL', 'DEBUG'))
formatter = logging.Formatter('%(asctime)s - %(module)s:%(funcName)s:%(lineno)d - [%(process)d][%(threadName)s] - %(levelname)s: %(message)s')

general_handler = logging.StreamHandler(sys.stdout)
general_filter = SingleLevelFilter(logging.INFO, False)
general_handler.setFormatter(formatter)
general_handler.addFilter(general_filter)
log.addHandler(general_handler)

error_handler = logging.StreamHandler(sys.stderr)
error_filter = SingleLevelFilter(logging.WARNING)
error_handler.setFormatter(formatter)
error_handler.addFilter(error_filter)

log_dir = os.getenv('LOG_LOCATION', os.getcwd())
if not os.path.exists(log_dir):
    os.mkdir(log_dir)
print('Log dir will be ' + log_dir)
#error_file_handler = logging.FileHandler(os.path.join(log_dir, 'error.log'))
#error_file_handler.setLevel(logging.ERROR)
#error_file_handler.setFormatter(formatter)

log.addHandler(error_handler)
#log.addHandler(error_file_handler)

log.propagate = False