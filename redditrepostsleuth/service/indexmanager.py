import os
from datetime import datetime

from redditrepostsleuth.common.logging import log
from redditrepostsleuth.common.config import config
from redditrepostsleuth.common.db.uow.unitofworkmanager import UnitOfWorkManager
from annoy import AnnoyIndex

class IndexManager:

    def __init__(self, uowm: UnitOfWorkManager):
        self.uowm = uowm
        self.temp_index = os.path.join(os.getcwd(), 'index_build.ann')

    def build_index(self):
        log.info('Building Image index')
        index = AnnoyIndex(64)

        if os.path.isfile(self.temp_index):
            log.info('Deleting existing index file')
            os.remove(self.temp_index)

        index.on_disk_build(self.temp_index)
        start = datetime.now()
        with self.uowm.start() as uow:
            delta = datetime.now() - start
            #log.info('%s: Loaded %s images in %s seconds', os.getpid(), len(existing_images), delta.seconds)
            log.info('Adding images to index')
            for image in uow.posts.yield_test():
                vector = list(bytearray(image[1], encoding='utf-8'))
                index.add_item(image[0], vector)
            log.info('Building index')
            index.build(config.index_tree_count)
            delta = datetime.now() - start
            log.info('Total index build time was %s seconds with images', delta.seconds)

    def run(self):
        self.build_index()
        while True:
            if os.path.isfile(os.path.join(os.getcwd(), 'index_build.ann')):
                log.info('Found temp index, promoting to main index')
                if os.path.isfile(config.index_file_name):
                    log.info('Deleting existing index file')
                    os.remove(config.index_file_name)
                os.rename(self.temp_index, os.path.join(os.getcwd(), config.index_file_name))
            self.build_index()