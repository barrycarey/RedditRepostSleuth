import json
import zstd

from redditrepostsleuth.common.celery.tasks import save_pushshift_results_archive

with open("/home/barry/Downloads/RS_2018-12.zst", 'rb') as fh:
    dctx = zstd.ZstdDecompressor()
    with dctx.stream_reader(fh) as reader:
        previous_line = ""
        batch = []
        while True:
            chunk = reader.read(2**24)
            if not chunk:
                break

            string_data = chunk.decode('utf-8')
            lines = string_data.split("\n")
            for i, line in enumerate(lines[:-1]):
                if i == 0:
                    line = previous_line + line
                object = json.loads(line)
                batch.append(object)

                if len(batch) >= 1000:
                    save_pushshift_results_archive.apply_async((batch,), queue='pushshift_intake')
                    batch = []
                    print('Sent batch to celery')
                # do something with the object here
            previous_line = lines[-1]

        save_pushshift_results_archive.apply_async((batch,), queue='pushshift_intake')
        batch = []
        print('sent last batch')