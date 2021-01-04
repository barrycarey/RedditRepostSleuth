import json

from redditrepostsleuth.core.model.image_search_results import ImageSearchResults


class ImageRepostWrapperEncoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, ImageSearchResults):
            return o.to_dict()