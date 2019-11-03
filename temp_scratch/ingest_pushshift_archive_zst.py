import json
import time
import zstd

import redis
from datetime import datetime

from influxdb import InfluxDBClient

from redditrepostsleuth.core.celery.tasks import save_pushshift_results_archive
from redditrepostsleuth.core.config import config

client = redis.Redis(host=config.redis_host, port=6379, db=0, password=config.redis_password)
influx = InfluxDBClient('monitor.ho.me', '8086', database='collectd')

def get_memeory():
    keys = ['pushshift_intake', 'pushshift_ingest', 'postingest', 'repost_image']
    used_bytes = 0
    for key in keys:
        used = client.memory_usage(key)
        if used:
            used_bytes = used_bytes + used
    total = used_bytes / 1024 / 1024 / 1024
    print(str(round(total, 2)))
    return total
r = influx.query('SELECT mean("value") FROM "redis_value" WHERE ("type" = \'memory\') AND time >= now() - 15m GROUP BY time(10s) fill(null)')
total = r.raw['series'][-1]['values'][1][1]

with open("/home/barry/Downloads/RS_2018-11.zst", 'rb') as fh:
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
                if object['created_utc'] < 1542167934:
                    continue
                batch.append(object)

                if len(batch) >= 1000:
                    save_pushshift_results_archive.apply_async((batch,), queue='pushshift_intake')

                    print('Sent batch to celery: ' + str(datetime.utcfromtimestamp(batch[0]['created_utc'])) + ' (' + str(object['created_utc']) + ')' )
                    batch = []

                    while True:
                        r = influx.query(
                            'SELECT mean("value") FROM "redis_value" WHERE ("type" = \'memory\') AND time >= now() - 15m GROUP BY time(10s) fill(null)')
                        total = r.raw['series'][0]['values'][-2][1]
                        if total and total >= 12884901888:
                            print('Waiting for memory to lower: ' + str(total / 1024 / 1024 / 1024))
                            time.sleep(20)
                        else:
                            break

                # do something with the object here
            previous_line = lines[-1]

        save_pushshift_results_archive.apply_async((batch,), queue='pushshift_intake')
        batch = []
        print('sent last batch')

