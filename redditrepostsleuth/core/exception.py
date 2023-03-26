
class RepostSleuthException(Exception):
    pass

class ImageConversioinException(RepostSleuthException):

    def __init__(self, message):
        super(ImageConversioinException, self).__init__(message)

class FutureDataRepostCheckException(RepostSleuthException):
    def __init__(self, message):
        super(FutureDataRepostCheckException, self).__init__(message)

class CrosspostRepostCheck(RepostSleuthException):
    def __init__(self, message):
        super(CrosspostRepostCheck, self).__init__(message)

class NoIndexException(RepostSleuthException):
    def __init__(self, message):
        super(NoIndexException, self).__init__(message)

class SubmissionNotFoundException(RepostSleuthException):
    def __init__(self, message):
        super(SubmissionNotFoundException, self).__init__(message)

class RateLimitException(RepostSleuthException):
    def __init__(self, message):
        super(RateLimitException, self).__init__(message)

class InvalidImageUrlException(RepostSleuthException):
    def __init__(self, message):
        super(InvalidImageUrlException, self).__init__(message)

class ImageRemovedException(RepostSleuthException):
    def __init__(self, message):
        super(ImageRemovedException, self).__init__(message)

class InvalidCommandException(RepostSleuthException):
    def __init__(self, message):
        super(InvalidCommandException, self).__init__(message)

class IngestHighMatchMeme(RepostSleuthException):
    def __init__(self, message):
        super(IngestHighMatchMeme, self).__init__(message)

class ReplyFailedException(RepostSleuthException):
    def __init__(self, message, reason):
        self.reason = reason
        super(ReplyFailedException, self).__init__(message)

class LoadSubredditException(RepostSleuthException):
    def __init__(self, message):
        super(LoadSubredditException, self).__init__(message)

class NoProxyException(RepostSleuthException):
    def __init__(self, message):
        super(NoProxyException, self).__init__(message)