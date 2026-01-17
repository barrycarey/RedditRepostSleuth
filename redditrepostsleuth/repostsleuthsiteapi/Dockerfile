FROM python:3.11-bookworm
MAINTAINER Barry Carey <mcarey66@gmail.com>

VOLUME /src/
ADD sleuth_config_dev.json /src/sleuth_config.json
COPY /redditrepostsleuth/repostsleuthsiteapi/requirements.txt /src/
ADD redditrepostsleuth /src/redditrepostsleuth/
WORKDIR /src

RUN apt-get update && apt-get install -y \
    libgl1-mesa-glx \
     && pip install -r requirements.txt

EXPOSE 8888

CMD ["gunicorn", "--bind", "0.0.0.0:8888", "--workers", "4", "--threads", "2", "redditrepostsleuth.repostsleuthsiteapi.app:api"]