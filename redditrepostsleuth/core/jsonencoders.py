import json

from redditrepostsleuth.core.model.search.image_search_results import ImageSearchResults


class ImageRepostWrapperEncoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, ImageSearchResults):
            return o.to_dict()