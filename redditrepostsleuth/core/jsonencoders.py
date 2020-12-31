import json

from redditrepostsleuth.core.model.search_results.image_post_search_match import ImagePostSearchMatch
from redditrepostsleuth.core.model.image_search_results import ImageSearchResults


class ImageMatchJsonEncoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, ImagePostSearchMatch):
            return o.to_dict()

class ImageRepostWrapperEncoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, ImageSearchResults):
            return o.to_dict()