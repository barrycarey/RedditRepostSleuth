FROM python:3.8.6-buster
MAINTAINER Barry Carey <mcarey66@gmail.com>

VOLUME /src/
COPY sleuth_config.json /src/
COPY /redditrepostsleuth/repostsleuthsiteapi/requirements.txt /src/
ADD redditrepostsleuth /src/redditrepostsleuth/
WORKDIR /src

RUN apt-get update && apt-get install -y \
    libgl1-mesa-glx \
     && pip install -r requirements.txt