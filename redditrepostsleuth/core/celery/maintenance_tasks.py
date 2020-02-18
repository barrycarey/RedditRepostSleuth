import random
from typing import List, Text, NoReturn

import requests

from redditrepostsleuth.core.celery import celery
from redditrepostsleuth.core.celery.basetasks import SqlAlchemyTask
from redditrepostsleuth.core.db.databasemodels import RedditImagePostCurrent, RedditImagePost
from redditrepostsleuth.core.logging import log
from redditrepostsleuth.core.util.constants import USER_AGENTS


@celery.task(bind=True, base=SqlAlchemyTask)
def cleanup_removed_posts_batch(self, posts: List[RedditImagePost]) -> NoReturn:
    with self.uowm.start() as uow:
        for image_post in posts:
            post = uow.posts.get_by_post_id(image_post)
            if not post:
                continue

            try:
                headers = {'User-Agent': random.choice(USER_AGENTS)}
                r = requests.head(post.url, timeout=3, headers=headers)
                if r.status_code == 404:
                    try:
                        uow.image_post.remove(image_post)
                        uow.commit()
                    except Exception as e:
                        log.exception('Failed to delete image post', exc_info=True)
            except Exception as e:
                continue