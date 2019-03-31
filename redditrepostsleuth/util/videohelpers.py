import os
import shutil
import uuid
from typing import Tuple

import requests
import sys

import ffmpeg
from youtube_dl import YoutubeDL

from redditrepostsleuth.common.logging import log



def generate_thumbnails_from_url(url: str, output_dir: str, total_thumbs: int = 20) -> int:

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

def generate_thumbnails_from_file(video_file: str, total_thumbs: int = 20) -> int:
    result = {
        'duration': None,
        'thumbs': []
    }
    try:
        probe = ffmpeg.probe(video_file)
    except Exception as e:
        log.error('Failed to probe video: %s', video_file)
        raise

    duration = float(probe['format']['duration'])
    interval = float(probe['format']['duration']) / total_thumbs
    count = 1
    seek = interval
    log.info('Video length is %s seconds. Grabbing thumb every %s seconds', duration, interval)

    output_dir = os.path.split(video_file)[0]

    while count <= total_thumbs:
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

def download_file(url: str, output_dir: str) -> Tuple[str, str]:
    """
    Take a URL to a video, download the file and return the path to the audio
    :param url: URL of video
    """


    ops = {
        'postprocessors': [
            {'key': 'FFmpegExtractAudio'}
        ],
        'outtmpl': os.path.join(output_dir, '%(id)s.%(ext)s'),
        'keepvideo': True
    }

    ydl = YoutubeDL(ops)
    try:
        ydl.download([url])
    except Exception as e:
        log.error('Failed to download %s', url)
        shutil.rmtree(output_dir)
        raise

    audio_file = None
    video_file = None
    video_exts = ['.mp4']
    audio_exts = ['.m4a', '.mp3']
    for f in os.listdir(output_dir):
        if os.path.splitext(f)[1] in video_exts:
            video_file = os.path.join(output_dir, f)
        elif os.path.splitext(f)[1] in audio_exts:
            audio_file = os.path.join(output_dir, f)

    return audio_file, video_file
