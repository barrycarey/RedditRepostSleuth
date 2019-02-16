import sys

from distance import hamming

from redditrepostsleuth.common.logging import log
from redditrepostsleuth.config import config
from redditrepostsleuth.db.uow.unitofworkmanager import UnitOfWorkManager
from datetime import datetime

from redditrepostsleuth.util.objectmapping import post_to_hashwrapper, hash_tuple_to_hashwrapper
from redditrepostsleuth.util.vptree import VPTree


class CashedVpTree:
    """
    Class to cache VP Tree of existing images
    """
    def __init__(self, uowm: UnitOfWorkManager):
        self.uowm = uowm
        self.building_tree = False
        self.tree_built_at = None
        self.vp_tree = None
        self.aged_vp_tree = None
        self.aged_vp_tree_newest = None

    @property
    def get_tree(self):
        if self.tree_built_at:
            last_built_seconds = datetime.now() - self.tree_built_at
            log.info('Tree built %s seconds ago', last_built_seconds.seconds)
        if self.tree_built_at is None or (datetime.now() - self.tree_built_at).seconds > config.vptree_cache_duration:
            log.info('Building New VPTree')
            with self.uowm.start() as uow:
                existing_images = uow.posts.test_with_entities()
                log.info('Tree will be built with %s images', len(existing_images))
                self.building_tree = True
                start = datetime.now()
                self.vp_tree = VPTree([hash_tuple_to_hashwrapper(post) for post in existing_images], lambda x,y: hamming(x,y))
                self.building_tree = False
                delta = datetime.now() - start
                print('Tree built in {} seconeds'.format(str(delta.seconds)))
                self.tree_built_at = datetime.now()
                return self.vp_tree
        else:
            log.info('Returning cached VP Tree')
            return self.vp_tree

    def get_aged_tree(self, date):
        log.info('Building new Aged VP Tree')
        with self.uowm.start() as uow:
            existing_images = uow.posts.find_all_older(date)
            log.info('Tree will be built with %s images', len(existing_images))
            start = datetime.now()
            tree = VPTree([hash_tuple_to_hashwrapper(post) for post in existing_images], lambda x,y: hamming(x,y))
            delta = datetime.now() - start
            print('Tree built in {} seconeds'.format(str(delta.seconds)))
            return tree


class CashedVpTreeTiered:

    def __init__(self, uowm: UnitOfWorkManager):
        self.uowm = uowm
        self.tree_built_at = None
        sys.setrecursionlimit(10000)
        self.trees = {
            '100': {
                'tree': None,
                'range': (0,100)
            },
            '200': {
                'tree': None,
                'range': (101, 200)
            },
            '300': {
                'tree': None,
                'range': (201, 300)
            },
            '400': {
                'tree': None,
                'range': (301, 400)
            },
            '500': {
                'tree': None,
                'range': (401, 500)
            },
            '600': {
                'tree': None,
                'range': (501, 600)
            },
            '700': {
                'tree': None,
                'range': (601, 700)
            },
        }

        # TODO: different queue for each tree

    @property
    def get_tree(self):
        if self.tree_built_at is None or (datetime.now() - self.tree_built_at).seconds > config.vptree_cache_duration:
            log.info('Building New VPTree')
            with self.uowm.start() as uow:
                total_start = datetime.now()
                for tree, value in self.trees.items():

                    start = datetime.now()
                    items = uow.posts.find_image_hashes_in_rage(value['range'][0], value['range'][1])
                    log.info('Building VPTree for range %s with %s items', tree, len(items))
                    value['tree'] = VPTree([hash_tuple_to_hashwrapper(post) for post in items], lambda x,y: hamming(x,y))
                    delta = datetime.now() - start
                    print('Tree built in {} seconeds'.format(str(delta.seconds)))
                delta = datetime.now() - total_start
                print('Total tree build time in {} seconds'.format(str(delta.seconds)))
                self.tree_built_at = datetime.now()

        return self.trees