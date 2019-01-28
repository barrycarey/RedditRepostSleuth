from datetime import datetime

from praw import Reddit
from praw.models import Submission

from redditrepostsleuth.db.model.post import Post
from redditrepostsleuth.db.uow.unitofworkmanager import UnitOfWorkManager


class PostIngest:
    def __init__(self, reddit: Reddit, uowm: UnitOfWorkManager) -> None:
        self.existing_posts = []
        self.reddit = reddit
        self.uowm = uowm

    def run(self):
        sr = self.reddit.subreddit('all')
        for post in sr.stream.submissions():

            self.store_post(post)

    def store_post(self, reddit_post: Submission):
        with self.uowm.start() as uow:
            if uow.posts.get_by_post_id(reddit_post.id):
                return
            post = Post()
            post.post_id = reddit_post.id
            post.url = reddit_post.url
            post.author = reddit_post.author.name if reddit_post.author else None
            post.created_at = datetime.fromtimestamp(reddit_post.created)
            post.subreddit = reddit_post.subreddit.display_name
            post.title = reddit_post.title
            post.perma_link = reddit_post.permalink
            if reddit_post.is_self:
                post.post_type = 'text'
            else:
                if hasattr(reddit_post, 'post_hint'):
                    post.post_type = reddit_post.post_hint
                else:
                    print('Missing Post Hint')
            if hasattr(reddit_post, 'crosspost_parent'):
                post.crosspost_parent = reddit_post.crosspost_parent

            uow.posts.add(post)
            try:
                uow.commit()
            except Exception as e:
                print('Failed to commit')
                uow.rollback()