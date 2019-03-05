import sys
import os

import ffmpeg

from redditrepostsleuth.db import db_engine
from redditrepostsleuth.db.uow.sqlalchemyunitofworkmanager import SqlAlchemyUnitOfWorkManager
from redditrepostsleuth.util.helpers import get_reddit_instance

reddit = get_reddit_instance()

sub = reddit.submission(id='akixg2')





uowm = SqlAlchemyUnitOfWorkManager(db_engine)

with uowm.start() as uow:
    posts = uow.posts.find_all_by_type('hosted:video', limit=50)

for post in posts:
    sub = reddit.submission(id=post.post_id)
    probe = ffmpeg.probe(sub.media['reddit_video']['fallback_url'])
    out_dir = os.path.join(os.getcwd(), 'video', post.post_id)
    os.mkdir(out_dir)

    interval = float(probe['format']['duration']) / 20
    count = 1
    seek = interval

    (
        ffmpeg
            .input(sub.media['reddit_video']['fallback_url'])
            .filter('scale', 720, -1)
            .output(os.path.join(out_dir, '{}.png'.format(str(count))), vframes=1)
            .overwrite_output()
            .run(capture_stdout=True, capture_stderr=True)
    )

    while count <= 20:

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