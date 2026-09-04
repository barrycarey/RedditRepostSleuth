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
        with self.uowm.start() as uow:
            nsfw = req.get_param_as_bool('nsfw', required=False)
            image_posts = uow.posts.get_newest_by_type(
                2,
                req.get_param_as_int('limit', default=20, required=False),
                req.get_param_as_int('offset', default=None, required=False),
                nsfw=nsfw
            )
            resp.body = json.dumps([p.to_dict() for p in image_posts])

    def on_get_reddit(self, req: Request, resp: Response):
        post_id = req.get_param('post_id', required=True)
        post = self.reddit.submission(post_id)
        if not post:
            raise HTTPNotFound(title='Post not found', description='Post not found on Reddit')

        # Handle deleted author
        author_name = None
        if post.author:
            author_name = post.author.name

        resp.body = json.dumps({
            'post_id': post.id,
            'title': post.title,
            'author': author_name,
            'subreddit': post.subreddit.display_name,
            'url': post.url,
            'permalink': f'https://reddit.com{post.permalink}',
            'image_url': post.url,
            'thumbnail_url': post.thumbnail if post.thumbnail not in ('self', 'default', 'nsfw', 'spoiler') else None,
            'created_at': datetime.utcfromtimestamp(post.created_utc).isoformat(),
            'score': post.score,
            'num_comments': post.num_comments,
            'is_nsfw': post.over_18
        })