import os
from datetime import datetime

from annoy import AnnoyIndex

from redditrepostsleuth.common.logging import log
from redditrepostsleuth.config import config
from redditrepostsleuth.db.uow.unitofworkmanager import UnitOfWorkManager


def build_image_index(uowm: UnitOfWorkManager, index_path: str) -> None:
    log.info('Starting image index task')
    if os.path.isfile(index_path):
        log.error('Temp index file already exists, removing it.')
        os.remove(index_path)

    index = AnnoyIndex(64)
    index.on_disk_build(index_path)
    with uowm.start() as uow:
        start = datetime.now()

        existing_images = uow.posts.load_all_image_hashes()

        delta = datetime.now() - start
        log.info('Loaded %s images in %s seconds', len(existing_images), delta.seconds)
        log.info('Adding hashes to index')
        for image in existing_images:
            vector = list(bytearray(image[1], encoding='utf-8'))
            index.add_item(image[0], vector)

        log.info('Building index')
        index.build(config.index_tree_count)
        delta = datetime.now() - start
        log.info('Total index build time was %s seconds', delta.seconds)

