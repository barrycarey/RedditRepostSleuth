FROM python:3.11-bookworm
LABEL maintainer="Barry Carey <mcarey66@gmail.com>"

VOLUME /src/
COPY sleuth_config.json /src/
COPY redditrepostsleuth/hotpostsvc/requirements.txt /src/
ADD redditrepostsleuth /src/redditrepostsleuth/
WORKDIR /src

RUN apt-get update && apt-get install -y \
    build-essential \
    libssl-dev \
    libffi-dev \
    python3-dev && pip install --no-cache-dir -r requirements.txt
