FROM python:3.11.3-buster
MAINTAINER Barry Carey <mcarey66@gmail.com>

VOLUME /src/
COPY sleuth_config_dev.json /src/
COPY /redditrepostsleuth/summonssvc/requirements.txt /src/
ADD redditrepostsleuth /src/redditrepostsleuth/
WORKDIR /src

RUN pip install -r requirements.txt
