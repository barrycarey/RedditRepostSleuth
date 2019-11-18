FROM python:3.7.4-buster
MAINTAINER Barry Carey <mcarey66@gmail.com>

VOLUME /src/
COPY sleuth_config.json /src/
COPY /wiki/bot_config.md /src/redditrepostsleuth/adminsvc/
COPY /wiki/stats.md /src/redditrepostsleuth/adminsvc/
COPY redditrepostsleuth/adminsvc/requirements.txt /src/
ADD redditrepostsleuth /src/redditrepostsleuth/
WORKDIR /src

RUN pip install -r requirements.txt

CMD ["python", "-u", "/src/redditrepostsleuth/adminsvc/adminsvc.py"]