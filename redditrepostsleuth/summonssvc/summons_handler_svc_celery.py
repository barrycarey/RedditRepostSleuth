# TODO - Mega hackery, figure this out.
import sys
import time

import redis
from redis.exceptions import ConnectionError


sys.path.append('./')
from redditrepostsleuth.core.celery.response_tasks import process_summons
from redditrepostsleuth.core.config import Config
from redditrepostsleuth.core.db.db_utils import get_db_engine
from redditrepostsleuth.core.db.uow.sqlalchemyunitofworkmanager import SqlAlchemyUnitOfWorkManager
from redditrepostsleuth.core.logging import log



if __name__ == '__main__':
    config = Config()
    uowm = SqlAlchemyUnitOfWorkManager(get_db_engine(config))

    redis_client = redis.Redis(host=config.redis_host, port=config.redis_port, db=config.redis_database, password=config.redis_password)
    while True:
        try:
            with uowm.start() as uow:
                summons = uow.summons.get_unreplied(limit=20)

                for s in summons:
                    log.info('Starting summons %s', s.id)
                    process_summons.apply_async((s,), queue='summons')
                while True:
                    queued_items = redis_client.lrange('summons', 0, 20000)
                    if len(queued_items) == 0:
                        log.info('Summons queue empty.  Starting over')
                        time.sleep(60)
                        break
                    log.info('Summons queue still has %s tasks', len(queued_items))
                    time.sleep(15)
        except ConnectionError as e:
            log.exception('Error connecting to Redis')



