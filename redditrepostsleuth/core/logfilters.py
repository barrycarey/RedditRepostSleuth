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


class ContextFilter(logging.Filter):

    def __init__(self):
        super().__init__()
        self.trace_id = 'None'
        self.post_id = 'None'
        self.subreddit = 'None'
        self.service = None

    def filter(self, record):
        record.trace_id = self.trace_id
        record.post_id = self.post_id
        record.subreddit = self.subreddit
        record.service = self.service
        return True


class IngestContextFilter(ContextFilter):

    def __init__(self):
        super().__init__()
        self.post_type = None

    def filter(self, record):
        record.post_id = self.post_id
        record.subreddit = self.subreddit
        record.service = self.service
        record.post_type = self.post_type
        record.trace_id = self.trace_id
        return True
