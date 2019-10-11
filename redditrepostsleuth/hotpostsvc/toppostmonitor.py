from praw import Reddit

from redditrepostsleuth.common.db.uow.unitofworkmanager import UnitOfWorkManager
from redditrepostsleuth.common.exception import NoIndexException
from redditrepostsleuth.common.logging import log
from redditrepostsleuth.common.model.db.databasemodels import Post
from redditrepostsleuth.core.duplicateimageservice import DuplicateImageService


class TopPostMonitor:

    MESSAGE_TEMPLATE = 'This {post_type} has been seen {count} times\n\n' \
                        'Oldest post: {oldest}'

    def __init__(self, reddit: Reddit, uowm: UnitOfWorkManager, image_service: DuplicateImageService):
        self.reddit = reddit
        self.uowm = uowm
        self.image_service = image_service


    def monitor(self):
        while True:
            submissions = self.reddit.subreddit('all').top('day')
            with self.uowm.start() as uow:
                for sub in submissions:
                    post = uow.posts.get_by_post_id(sub.id)
                    if post and post.left_comment:
                        continue
                    self.check_for_repost(post)
                    uow.posts.update(post)
                    uow.commit()

    def check_for_repost(self, post: Post):
        try:
            results = self.image_service.check_duplicate(post)
        except NoIndexException:
            log.error('No available index for image repost check.  Trying again later')
            return

        print('')

    def check_image_repost(self, post: Post):
        pass

    def add_comment(self, data: dict) -> None:
        submission = self.reddit.submission([''])