import os

import ffmpeg


def generate_thumbnails(url: str, output_dir: str, total_thumbs: int = 20) -> None:

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