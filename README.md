# Reddit Repost Sleuth
###### A bot to monitor for and detect reposted content on Reddit

### How it works
The Repost Sleuth bot continually ingests all new posts and stores them in a database. It then uses various methods to find reposted content

##### Images
A difference hash is generated for each image that is ingested. We then use a hamming distance comparision to find matching images in the database

##### Links
We use the exact URL to find matches

##### Videos
Not currently supported

##### Text
Not currently supported

### Features
Repost Sleuth responds to various commands.  See command section below

* Ingest all new posts and comments
* Compare several posts types and determin if they are a repost
* Set watches on a post and get notifications if someone else posts the same thing
* More to come

### Commands
**!repost all message|comment** - Find all matching posts and list them in a comment reply or via PM

**!repost watch message|comment** - Monitor this post and notify you if we see it posted somewhere else

**!repost unwatch** - Disable an active repost monitors for this post

**!repost stats** - Get stats about the bot

### Technology

Repost Sleuth makes heavy use of Celery with a Redis backend.  Celery allows a large number of CPU bound tasks to be run in parallel with a number of benefits  

All data is store in a MySQL database and we use SQLAlchemy to interact with the data

Repost Sleuth is hosted in a Virtual machine on Dell hardware. The VM has 16 cores and 32gb of RAM.  The bot requires a large amount of CPU cores to efficiently deal with the workload.  The RAM is needed to store all images hashes in memory for fast searching

### Feature Suggestions
If you are interested in seeing a specific feature please open an issue 

### Contributing 

At the moment I'm not looking for any contributions. The code base is super messy and still pretty experimental. 