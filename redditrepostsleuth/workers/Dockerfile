FROM python:3.11.3-buster
MAINTAINER Barry Carey <mcarey66@gmail.com>

VOLUME /src/
ADD sleuth_config.json /src/
ADD worker-requirements.txt /src/requirements.txt
ADD redditrepostsleuth /src/redditrepostsleuth/
WORKDIR /src

RUN install -r requirements.txt
