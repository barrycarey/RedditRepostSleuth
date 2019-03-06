import shutil
import sys
import os
from datetime import datetime
from os import listdir

import ffmpeg
import imagehash

from redditrepostsleuth.db import db_engine
from redditrepostsleuth.db.uow.sqlalchemyunitofworkmanager import SqlAlchemyUnitOfWorkManager
from redditrepostsleuth.model.db.databasemodels import VideoHash

from redditrepostsleuth.util.helpers import get_reddit_instance
from redditrepostsleuth.util.imagehashing import generate_img_by_file
from redditrepostsleuth.util.videohelpers import generate_thumbnails

reddit = get_reddit_instance()

sub = reddit.submission(id='akixg2')





uowm = SqlAlchemyUnitOfWorkManager(db_engine)

with uowm.start() as uow:
    posts = uow.posts.find_all_by_type('hosted:video', offset=2500, limit=10)

start = datetime.now()
for post in posts:
    sub = reddit.submission(id=post.post_id)
    url = sub.media['reddit_video']['fallback_url']
    out_dir = os.path.join(os.getcwd(), 'video', post.post_id)

    try:
        generate_thumbnails(url, out_dir)
    except Exception as e:
        print('Failed to make thumbnaisl for ' + post.post_id)
        continue

    hashes = []
    for thumb in listdir(out_dir):
        img = generate_img_by_file(os.path.join(out_dir, thumb))
        dhash = str(imagehash.dhash(img, hash_size=16))
        hashes.append(dhash)


    shutil.rmtree(out_dir)

    video_hash = VideoHash()
    video_hash.post_id = post.post_id
    video_hash.hashes = ','.join(hashes)

    with uowm.start() as uow:
        uow.video_hash.add(video_hash)
        uow.commit()

"""
start = datetime.now()
for post in posts:
    sub = reddit.submission(id=post.post_id)
    try:
        probe = ffmpeg.probe(sub.media['reddit_video']['fallback_url'])
    except Exception:
        print('error: ' + post.post_id)
        continue
    out_dir = os.path.join(os.getcwd(), 'video', post.post_id)
    if not os.path.isdir(out_dir):
        os.mkdir(out_dir)

    duration = float(probe['format']['duration'])
    interval = float(probe['format']['duration']) / 20
    count = 1
    seek = interval
    sample = (duration * 30) / 20
    (
        ffmpeg
            .input(sub.media['reddit_video']['fallback_url'])
            .filter('thumbnail', sample)
            .filter('setpts', 'N/TB')
            .output(os.path.join(out_dir, '{}-%03d.png'.format(str(count))), vframes=20, r=1)
            .overwrite_output()
            .run(capture_stdout=True, capture_stderr=True)
    )

delta = datetime.now() - start
print('First run took ' + str(delta.seconds))
"""
"""
start = datetime.now()
for post in posts:
    print(post.post_id)
    sub = reddit.submission(id=post.post_id)
    probe = ffmpeg.probe(sub.media['reddit_video']['fallback_url'])
    out_dir = os.path.join(os.getcwd(), 'video', post.post_id)
    if not os.path.isdir(out_dir):
        os.mkdir(out_dir)

    duration = float(probe['format']['duration'])
    interval = float(probe['format']['duration']) / 20
    count = 1
    seek = interval
    while count <= 20:
        print(str(count))
        try:
            (
                ffmpeg
                    .input(sub.media['reddit_video']['fallback_url'], ss=seek)
                    .filter('scale', 720, -1)
                    .output(os.path.join(out_dir, '{}.png'.format(str(count))), vframes=1)
                    .overwrite_output()
                    .run(capture_stdout=True, capture_stderr=True)
            )
        except ffmpeg.Error as e:
            print(e.stderr.decode(), file=sys.stderr)
            sys.exit(1)

        seek += interval
        count += 1

delta = datetime.now() - start
print('Second run took ' + str(delta.seconds))
"""