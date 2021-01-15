FROM python:3.8.7-buster
MAINTAINER Barry Carey <mcarey66@gmail.com>

VOLUME /src/
COPY sleuth_config.json /src/
COPY /redditrepostsleuth/summonssvc/requirements.txt /src/
ADD redditrepostsleuth /src/redditrepostsleuth/
WORKDIR /src

RUN apt-get update && apt-get install -y \
    build-essential \
    libssl-dev \
    libffi-dev \
    python-dev && pip install -r requirements.txt

CMD ["python", "-u", "/src/redditrepostsleuth/summonssvc/summonssvc.py"]