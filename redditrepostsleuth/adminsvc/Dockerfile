FROM python:3.11.2-buster
MAINTAINER Barry Carey <mcarey66@gmail.com>

VOLUME /src/
COPY sleuth_config.json /src/
COPY /wiki/bot_config.md /src/
COPY /wiki/banned-subs.md /src/
COPY /wiki/stats.md /src/
COPY redditrepostsleuth/adminsvc/requirements.txt /src/
ADD redditrepostsleuth /src/redditrepostsleuth/
WORKDIR /src

RUN pip install -r requirements.txt
