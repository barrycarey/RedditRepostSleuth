FROM python:3.7.4-buster
MAINTAINER Barry Carey <mcarey66@gmail.com>

VOLUME /src/
COPY testconfig.ini requirements.txt /src/
ADD redditrepostsleuth /src/redditrepostsleuth/
WORKDIR /src

RUN apt-get update && apt-get install -y \
    build-essential \
    libssl-dev \
    libffi-dev \
    python-dev && pip install -r requirements.txt

