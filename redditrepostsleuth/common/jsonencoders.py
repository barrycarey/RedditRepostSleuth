import json

from redditrepostsleuth.common.model.imagematch import ImageMatch
from redditrepostsleuth.common.model.imagerepostwrapper import ImageRepostWrapper


class ImageMatchJsonEncoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, ImageMatch):
            return o.to_dict()

class ImageRepostWrapperEncoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, ImageRepostWrapper):
            return o.to_dict()