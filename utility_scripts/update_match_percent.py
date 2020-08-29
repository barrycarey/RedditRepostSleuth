import json
import time
from json import JSONDecodeError

import requests

from redditrepostsleuth.core.config import Config
from redditrepostsleuth.core.db.db_utils import get_db_engine
from redditrepostsleuth.core.db.uow.sqlalchemyunitofworkmanager import SqlAlchemyUnitOfWorkManager
from redditrepostsleuth.core.duplicateimageservice import DuplicateImageService
from redditrepostsleuth.core.services.eventlogging import EventLogging
from redditrepostsleuth.core.services.reddit_manager import RedditManager
from redditrepostsleuth.core.services.response_handler import ResponseHandler
from redditrepostsleuth.core.services.responsebuilder import ResponseBuilder
from redditrepostsleuth.core.util.imagehashing import get_image_hashes
from redditrepostsleuth.core.util.reddithelpers import get_reddit_instance
from redditrepostsleuth.submonitorsvc.submonitor import SubMonitor

config = Config(r'/home/barry/PycharmProjects/RedditRepostSleuth/sleuth_config.json')
reddit = get_reddit_instance(config)
uowm = SqlAlchemyUnitOfWorkManager(get_db_engine(config))
reddit_manager = RedditManager(reddit)
event_logger = EventLogging(config=config)
response_handler = ResponseHandler(reddit_manager, uowm, event_logger, source='submonitor')
dup_image_svc = DuplicateImageService(uowm, event_logger, config=config)
response_builder = ResponseBuilder(uowm)
sub_monitor = SubMonitor(dup_image_svc, uowm, reddit_manager, response_builder, response_handler, event_logger=event_logger, config=config)

with uowm.start() as uow:
    post = uow.posts.get_by_post_id('iirpkm')
    target_hashes = get_image_hashes(post, hash_size=32)


with uowm.start() as uow:
    monitored_subs = uow.monitored_sub.get_all()
    for sub in monitored_subs:
        sub.target_image_match = 100 - (sub.target_hamming / 64) * 100
