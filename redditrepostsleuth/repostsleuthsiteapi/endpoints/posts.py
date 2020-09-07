import json
from datetime import datetime
from typing import Text

from falcon import Request, Response, HTTPNotFound
from praw import Reddit

from redditrepostsleuth.core.db.uow.unitofworkmanager import UnitOfWorkManager
from redditrepostsleuth.core.services.reddit_manager import RedditManager


class PostsEndpoint:
    def __init__(self, uowm: UnitOfWorkManager, reddit: RedditManager):
        self.uowm = uowm
        self.reddit = reddit

    def on_get(self, req: Request, resp: Response):
        with self.uowm.start() as uow:
            post = uow.posts.get_by_post_id(req.get_param('post_id', required=True))
            if not post:
                raise HTTPNotFound(title='Post not found', description=f'This post was not found in the Repost Sleuth Database')
            resp.body = json.dumps(post.to_dict())

    def on_get_all(self, req: Request, resp: Response):
        result = []
        with self.uowm.start() as uow:
            image_posts = uow.image_post.get_all(
                req.get_param_as_int('limit', default=20, required=False),
                req.get_param_as_int('offset', default=None, required=False)
            )
            for ip in image_posts:
                post = uow.posts.get_by_post_id(ip.post_id)
                result.append(post.to_dict())


            resp.body = json.dumps(result)

    def on_get_reddit(self, req: Request, resp: Response):
        post = self.reddit.submission(req.get_param('post_id', required=True))
        if not post:
            raise HTTPNotFound()

        resp.body = json.dumps({
            'post_id': post.id,
            'author': post.author.name,
            'title': post.title,
            'url': post.url,
            'created_at': post.created_utc,
            'score': post.score
        })