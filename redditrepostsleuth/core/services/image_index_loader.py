import os
from datetime import datetime
from typing import Text

from annoy import AnnoyIndex

from redditrepostsleuth.core.config import Config
from redditrepostsleuth.core.exception import NoIndexException
from redditrepostsleuth.core.logging import log
from redditrepostsleuth.core.model.image_index import ImageIndex
from redditrepostsleuth.core.util.redlock import redlock


class ImageIndexLoader:

    def __init__(self, config: Config):
        self.config = config
        self.indexes = []
        self._init_indexes()


    def _init_indexes(self):
        self._current_index = ImageIndex(
            name='current',
            file_path=self.config.index_current_file,
            max_age=self.config.index_current_max_age,
            skip_load_seconds=self.config.index_current_skip_load_age
        )
        self.indexes.append(self._current_index)
        self._historical_index = ImageIndex(
            name='historical',
            file_path=self.config.index_historical_file,
            max_age=self.config.index_historical_max_age,
            skip_load_seconds=self.config.index_historical_skip_load_age
        )
        self.indexes.append(self._historical_index)
        self._meme_index = ImageIndex(
            name='meme',
            file_path=self.config.index_meme_file,
            max_age=self.config.index_meme_max_age,
            skip_load_seconds=self.config.index_meme_skip_load_age
        )
        self.indexes.append(self._meme_index)

    def _load_index(self, index: ImageIndex):
        log.debug('Attempting to load %s index', index.name)
        if index.built_at and (
                datetime.now() - index.built_at).seconds < index.skip_load_seconds:
            log.debug('Loaded %s index is less than %s old.  Skipping load attempt', index.name, index.skip_load_seconds)
            return

        if not os.path.isfile(index.file_path):
            if not index.built_at:
                log.error('No %s index loaded and none exists on disk', index.name)
                raise NoIndexException('No existing index found')
            elif index.built_at and (datetime.now() - index.built_at).seconds > index.max_age:
                log.error('Loaded %s index is too old and no new index found on disk', index.name)
                raise NoIndexException('No existing index found')
            else:
                log.info('No existing %s index found, using in memory index', index.name)
                return

        created_at = datetime.fromtimestamp(os.stat(index.file_path).st_ctime)
        delta = datetime.now() - created_at

        if delta.seconds > index.max_age:
            log.info('Existing %s index is too old.  Skipping repost check', index.name)
            raise NoIndexException(f'Existing {index.name} index is too old')

        if not index.built_at:
            with redlock.create_lock('index_load', ttl=30000):
                log.debug('Loading existing index')
                index.loaded_index = AnnoyIndex(64)
                index.loaded_index.load(index.file_path)
                index.built_at = created_at
                index.size = index.loaded_index.get_n_items()
                log.info('Loaded %s image index with %s items', index.name, index.loaded_index.get_n_items())
                return

        if created_at > index.built_at:
            log.info('Existing %s image index is newer than loaded index.  Loading new index', index.name)
            with redlock.create_lock('index_load', ttl=30000):
                log.info('Got index lock')
                index.loaded_index = AnnoyIndex(64)
                index.loaded_index.load(index.file_path)
                index.built_at = created_at
                log.debug('New %s index has %s items', index.name, index.loaded_index.get_n_items())
                if index.loaded_index.get_n_items() < index.size:
                    log.critical('New %s image index has less items than old. Aborting repost check', index.name)
                    raise NoIndexException(f'New {index.name} image index has less items than last index')
                index.size = index.loaded_index.get_n_items()

        else:
            log.debug('Loaded %s index is up to date.  Using with %s items', index.name, index.loaded_index.get_n_items())

    @property
    def historical_index(self) -> ImageIndex:
        self._load_index(self._historical_index)
        if self._historical_index.loaded_index.get_n_items() < 50000000:
            log.error('Loaded historical index is too small.  Only loaded %s items', self._historical_index.loaded_index.get_n_items())
            raise NoIndexException('Loaded historical index is smaller than expected')
        return self._historical_index

    @property
    def current_index(self) -> ImageIndex:
        self._load_index(self._current_index)
        return self._current_index

    @property
    def meme_index(self) -> ImageIndex:
        self._load_index(self._meme_index)
        return self._meme_index