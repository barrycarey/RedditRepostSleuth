import logging
import sys

from redditrepostsleuth.common.logfilters import SingleLevelFilter

log = logging.getLogger(__name__)
log.setLevel('DEBUG')
formatter = logging.Formatter('%(asctime)s - %(module)s:%(funcName)s:%(lineno)d - [%(threadName)s] - %(levelname)s: %(message)s')

general_handler = logging.StreamHandler(sys.stdout)
general_filter = SingleLevelFilter(logging.INFO, False)
general_handler.setFormatter(formatter)
general_handler.addFilter(general_filter)
log.addHandler(general_handler)

error_handler = logging.StreamHandler(sys.stderr)
error_filter = SingleLevelFilter(logging.WARNING)
error_handler.setFormatter(formatter)
error_handler.addFilter(error_filter)

error_file_handler = logging.FileHandler('error.log')
error_file_handler.setLevel(logging.ERROR)
error_file_handler.setFormatter(formatter)

log.addHandler(error_handler)
log.addHandler(error_file_handler)

log.propagate = False