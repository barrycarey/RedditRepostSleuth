import requests

from redditrepostsleuth.common.logging import log
from redditrepostsleuth.db.uow.unitofworkmanager import UnitOfWorkManager
from redditrepostsleuth.util.imagehashing import generate_img, generate_dhash


class ImageRepostProcessing:

    def __init__(self, uowm: UnitOfWorkManager) -> None:
        self.uowm = uowm

    def generate_hashes(self):
        """
        Load images without a hash from the database and create hashes
        """

        while True:
            with self.uowm.start() as uow:
                posts = uow.posts.find_all_by_hash(None, limit=200)
                log.info('Loaded %s images without hashes', len(posts))
                for post in posts:
                    img = generate_img(post)
                    if not img:
                        continue
                    post.image_hash = generate_dhash(img)
                    uow.commit()

    def clear_deleted_images(self):
        with self.uowm.start() as uow:
            while True:
                posts = uow.posts.find_all_by_type('image')
                for post in posts:
                    log.debug('Checking URL %s', post.url)
                    r = requests.get(post.url)
                    if r.status_code == 404:
                        log.debug('Deleting removed post (%s)', str(post))
                        uow.posts.remove(post)
                        uow.commit()