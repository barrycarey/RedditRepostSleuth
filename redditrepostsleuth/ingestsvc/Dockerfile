FROM python:3.11.3-buster
MAINTAINER Barry Carey <mcarey66@gmail.com>

VOLUME /src/
COPY sleuth_config.json /src/
COPY redditrepostsleuth/ingestsvc/requirements.txt /src/
ADD redditrepostsleuth /src/redditrepostsleuth/
WORKDIR /src

RUN pip install -r requirements.txt

CMD ["python", "-u", "/src/redditrepostsleuth/ingestsvc/ingestsvc.py"]