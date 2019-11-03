import logging


class SingleLevelFilter(logging.Filter):
    def __init__(self, passlevel, above=True):
        self.passlevel = passlevel
        self.above = above

    def filter(self, record):
        if self.above:
            return record.levelno >= self.passlevel
        else:
            return record.levelno <= self.passlevel