FROM python:3.7.4-buster
MAINTAINER Barry Carey <mcarey66@gmail.com>

VOLUME /src/
COPY testconfig.ini requirements.txt __init__.py /src/
ADD common /src/redditrepostsleuth/common/
ADD ingestsvc /src/redditrepostsleuth/ingestsvc/
ADD service /src/redditrepostsleuth/service/
WORKDIR /src

RUN apt-get update && apt-get install -y \
    build-essential \
    libssl-dev \
    libffi-dev \
    python-dev && pip install -r requirements.txt

CMD ["celery", "-A redditrepostsleuth.common worker", "-Q postingest,repost",  "-c 6"]