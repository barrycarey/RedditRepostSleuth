import os
import socket

import pymysql
from annoy import AnnoyIndex
from datetime import datetime

from redditrepostsleuth.common.config import config
from redditrepostsleuth.core.db import db_engine
from redditrepostsleuth.core.db import SqlAlchemyUnitOfWorkManager
from redditrepostsleuth.common.model.db import IndexBuildTimes

conn = pymysql.connect(host=config.db_host,
                             user=config.db_user,
                             password=config.db_password,
                             db=config.db_name,
                             cursorclass=pymysql.cursors.SSDictCursor,
                            autocommit=True)

uowm = SqlAlchemyUnitOfWorkManager(db_engine)


while True:

    build_time = IndexBuildTimes()
    build_time.index_type = 'image'
    build_time.hostname = socket.gethostname()

    if os.path.isfile('images_temp.ann'):
        print('Removing existing temp index')
        os.remove('images_temp.ann')
    index = AnnoyIndex(64)
    index.on_disk_build('images_temp.ann')
    start = datetime.now()
    build_time.build_start = start

    with conn.cursor() as cur:
        cur.execute("SELECT id, dhash_h FROM reddit_image_post")

        delta = datetime.now() - start
        print(f'Loaded records in {delta.seconds}')
        print(f' {datetime.now()} Adding items to index')
        index_start = datetime.now()
        count = 0
        for row in cur:
            vector = list(bytearray(row['dhash_h'], encoding='utf-8'))
            index.add_item(row['id'], vector)

        delta = datetime.now() - start
        print(f'{datetime.now()} Added All Items in {delta.seconds}')

        index.build(20)

        delta = datetime.now() - start
        build_time.build_minutes = delta.seconds / 60
        build_time.build_end = datetime.now()
        build_time.items = index.get_n_items()
        print(f'{datetime.now()} Built Index in {delta.seconds}')

        if os.path.isfile('images.ann'):
            print('Removing existing index file')
            os.remove('images.ann')

        os.rename('images_temp.ann', 'images.ann')
        print('Renamed temp index')

        with uowm.start() as uow:
            uow.index_build_time.add(build_time)
            uow.commit()