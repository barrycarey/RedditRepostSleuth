FROM python:3.8.7-buster
MAINTAINER Barry Carey <mcarey66@gmail.com>

VOLUME /src/
COPY sleuth_config.json /src/
COPY /redditrepostsleuth/workers/repost/requirements.txt /src/
ADD redditrepostsleuth /src/redditrepostsleuth/
WORKDIR /src

RUN apt-get update && apt-get install -y \
    build-essential \
    libssl-dev \
    libffi-dev \
    python-dev && pip install -r requirements.txt

ENTRYPOINT celery -A redditrepostsleuth.common worker -Q repost,repost_link -c 1