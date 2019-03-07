import os
import sys

import ffmpeg

from redditrepostsleuth.common.logging import log


def generate_thumbnails(url: str, output_dir: str, total_thumbs: int = 20) -> int:

    probe = ffmpeg.probe(url)

    if not os.path.isdir(output_dir):
        os.mkdir(output_dir)

    duration = float(probe['format']['duration'])
    interval = float(probe['format']['duration']) / 20
    sample = (duration * 30) / total_thumbs
    (
        ffmpeg
            .input(url)
            .filter('thumbnail', sample)
            .filter('setpts', 'N/TB')
            .output(os.path.join(output_dir, '%03d.png'), vframes=total_thumbs, r=1)
            .overwrite_output()
            .run(capture_stdout=True, capture_stderr=True)
    )

    return duration

def generate_thumbnails2(url: str, output_dir: str, total_thumbs: int = 20) -> int:

    probe = ffmpeg.probe(url)
    log.info('Generating thumbs: %s', url)
    if not os.path.isdir(output_dir):
        os.mkdir(output_dir)

    duration = float(probe['format']['duration'])
    interval = float(probe['format']['duration']) / 20
    count = 1
    seek = interval
    log.info('Video length is %s seconds. Grabbing thumb every %s seconds', duration, interval)
    while count <= 20:
        print(str(count))
        try:
            (
                ffmpeg
                    .input(url, ss=seek)
                    .filter('scale', 720, -1)
                    .output(os.path.join(output_dir, '{}.png'.format(str(count))), vframes=1)
                    .overwrite_output()
                    .run(capture_stdout=True, capture_stderr=True)
            )
        except ffmpeg.Error as e:
            print(e.stderr.decode(), file=sys.stderr)


        seek += interval
        count += 1

    return duration