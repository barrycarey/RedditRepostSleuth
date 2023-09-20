
class RepostSleuthException(Exception):
    pass

class ImageConversionException(RepostSleuthException):

    def __init__(self, message):
        super(ImageConversionException, self).__init__(message)

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

class UtilApiException(RepostSleuthException):
    def __init__(self, message):
        super(UtilApiException, self).__init__(message)

class IndexApiException(RepostSleuthException):
    def __init__(self, message):
        super(IndexApiException, self).__init__(message)

class GalleryNotProcessed(RepostSleuthException):
    def __init__(self, message):
        super(GalleryNotProcessed, self).__init__(message)

class UserNotFound(RepostSleuthException):
    def __init__(self, message):
        super(UserNotFound, self).__init__(message)