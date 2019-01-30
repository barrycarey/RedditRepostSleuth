import requests

from distance import hamming

from redditrepostsleuth.common.logging import log
from redditrepostsleuth.db.uow.unitofworkmanager import UnitOfWorkManager
from redditrepostsleuth.util.imagehashing import generate_img, generate_dhash
from redditrepostsleuth.util.vptree import VPTree


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
        while True:
            with self.uowm.start() as uow:
                posts = uow.posts.find_all_by_type('image')
                for post in posts:
                    log.debug('Checking URL %s', post.url)
                    try:
                        r = requests.get(post.url)
                        if r.status_code == 404:
                            log.debug('Deleting removed post (%s)', str(post))
                            uow.posts.remove(post)
                            uow.commit()
                    except Exception as e:
                        print('')

    def process_reposts(self):
        while True:
            hashes = []
            with self.uowm.start() as uow:
                unchecked_posts = uow.posts.find_all_by_repost_check(False, limit=100)
                hashed_images = uow.posts.find_all_images_with_hash()
                for hash in hashed_images:
                    hashes.append(hash.image_hash)

                log.info('Building VP Tree with %s objects', len(hashed_images))
                tree = VPTree(hashed_images, lambda x,y: hamming(x,y))
                for repost in unchecked_posts:
                    print('Checking Hash: ' + repost.image_hash)
                    repost.checked_repost = True
                    r = tree.get_all_in_range(repost.image_hash, 10)

                    if len(r) == 1:
                        continue
                    results = [x for x in r if x[0] < 10 and x[1].post_id != repost.post_id and x[1].crosspost_parent is None ]
                    if len(results) > 0:
                        print('Original: http://reddit.com' + repost.perma_link)
                        oldest = None
                        for i in results:
                            if oldest:
                                if oldest.created_at < i[1].created_at:
                                    oldest = i[1]
                            else:
                                  if i[1].created_at < repost.created_at:
                                      oldest = i[1]
                        if oldest is not None:
                            log.info('Found Repost.  http://reddit.com%s is a repost of http://reddit.com%s', repost.perma_link, oldest.perma_link)
                            repost.repost_of = oldest.id
                uow.commit()
