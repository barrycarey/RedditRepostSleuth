import requests
from pymilvus.grpc_gen.common_pb2 import Retry

from redditrepostsleuth.core.celery import celery
from redditrepostsleuth.core.celery.basetasks import MilvusTask
from redditrepostsleuth.core.logging import get_configured_logger

log = get_configured_logger(name='redditrepostsleuth')
@celery.task(bind=True, base=MilvusTask, ignore_reseults=True, serializer='pickle', autoretry_for=(ConnectionError,), retry_kwargs={'max_retries': 10, 'countdown': 300})
def fetch_and_save_embedding(self, image_data: str, post_id: str) -> None:


    try:
        self._check_milvus_connection()

        data = {
            'images': {
                'data': [image_data]
            }
        }

        response = requests.post(f'http://{self.config.embedding_api}/extract', json=data)

        if response.status_code != 200:
            log.error('Unexpected Status %s: %s', response.status_code, 'url')
            return

        result = response.json()
        if result['data'][0]['status'] != 'ok':
            log.warning('Failed Embed: %s - %s', result['data'][0]['traceback'], 'url')
            return
        embeddings = []
        for face in result['data'][0]['faces']:
            embeddings.append((post_id, face['vec'], face['bbox']))

        try:
            milvus_data = []
            for embed in embeddings:
                milvus_data.append({'embedding': embed[1], 'post_id': embed[0], 'bbox': embed[2]})
            if milvus_data:
                res = self.milvus_conn.insert('reddit_images', data=milvus_data)
                log.info('Saved embedding')
            else:
                log.info('No embeddings to save')
        except Exception as e:
            log.exception('')
    except (ConnectionError, Retry) as e:
        raise e
    except Exception as e:
        log.exception('')
