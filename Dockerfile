FROM python
MAINTAINER Matthew Carey <mcarey66@gmail.com>

VOLUME /src/
COPY redditrepostsleuth.py requirements.txt /src/
ADD redditrepostsleuth /src/redditrepostsleuth
WORKDIR /src

RUN pip install -r requirements.txt

CMD ["python3", "-u", "/src/plexcollector.py"]