import sys

import ffmpeg

probe = ffmpeg.probe('DASH_9_6_M.mp4')


interval = float(probe['format']['duration']) / 20
count = 1
seek = interval
while count <= 20:


    try:
        (
            ffmpeg
                .input('https://v.redd.it/codqh832t2d21/DASH_9_6_M?source=fallback', ss=seek)
                .filter('scale', 720, -1)
                .output('{}.png'.format(str(count)), vframes=1)
                .overwrite_output()
                .run(capture_stdout=True, capture_stderr=True)
        )
    except ffmpeg.Error as e:
        print(e.stderr.decode(), file=sys.stderr)
        sys.exit(1)


    seek += interval
    count += 1