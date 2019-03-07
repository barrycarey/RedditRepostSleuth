import os
import requests
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

    log.info('Generating thumbs: %s', url)
    if not os.path.isdir(output_dir):
        os.mkdir(output_dir)

    r = requests.get(url)
    video_file = os.path.join(output_dir, 'video.mp4')
    with open(video_file, 'wb') as f:
        f.write(r.content)

    try:
        probe = ffmpeg.probe(video_file)
    except Exception as e:
        log.error('Failed to probe video: %s', video_file)
        raise

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
                    .input(video_file, ss=seek)
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