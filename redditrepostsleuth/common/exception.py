
class RepostSleuthException(Exception):
    pass

class ImageConversioinException(RepostSleuthException):

    def __init__(self, message):
        super(ImageConversioinException, self).__init__(message)
