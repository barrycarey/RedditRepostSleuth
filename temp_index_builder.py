import os

import pymysql
from annoy import AnnoyIndex
from datetime import datetime

from redditrepostsleuth.config import config

conn = pymysql.connect(host=config.db_host,
                             user=config.db_user,
                             password=config.db_password,
                             db=config.db_name,
                             cursorclass=pymysql.cursors.SSDictCursor)




while True:
    if os.path.isfile('images_temp.ann'):
        print('Removing existing temp index')
        os.remove('images_temp.ann')
    index = AnnoyIndex(64)
    index.on_disk_build('images_temp.ann')
    start = datetime.now()

    with conn.cursor() as cur:
        cur.execute("SELECT id, dhash_h FROM reddit_image_post")

        delta = datetime.now() - start
        print(f'Loaded records in {delta.seconds}')
        print('Adding items to index')
        index_start = datetime.now()
        count = 0
        for row in cur:
            vector = list(bytearray(row['dhash_h'], encoding='utf-8'))
            index.add_item(row['id'], vector)

        delta = datetime.now() - start
        print(f'Added All Items in {delta.seconds}')

        index.build(20)

        delta = datetime.now() - start
        print(f'Built Index in {delta.seconds}')

        if os.path.isfile('images.ann'):
            print('Removing existing index file')
            os.remove('images.ann')

        os.rename('images_temp.ann', 'images.ann')
        print('Renamed temp index')