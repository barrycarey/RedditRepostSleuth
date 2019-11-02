import json
import time
import zstd

import redis
from datetime import datetime

from influxdb import InfluxDBClient
import sys

from redditrepostsleuth.common.celery.tasks import save_pushshift_results_archive
from redditrepostsleuth.common.config import config

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


if __name__ == '__main__':

        batch = []

        for line in sys.stdin:
            object = json.loads(line)

            if object['created_utc'] < 1519082075:
                continue


            batch.append(object)

            if len(batch) >= 1000:
                try:
                    save_pushshift_results_archive.apply_async((batch,), queue='pushshift_intake')
                except Exception as e:
                    time.sleep(20)
                    try:
                        save_pushshift_results_archive.apply_async((batch,), queue='pushshift_intake')
                    except Exception:
                        continue
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


        save_pushshift_results_archive.apply_async((batch,), queue='pushshift_intake')
        batch = []
        print('sent last batch')

