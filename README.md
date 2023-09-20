
<div align="center">
	<img width="600" height="auto" src="hero.png" alt="hero">
	<br>
	<h4>
		Check out <a href="https://repostsleuth.com">RepostSleuth.com</a> 
	</h4>
</div>

![Master](https://github.com/barrycarey/RedditRepostSleuth/workflows/Tests/badge.svg)
![semver](https://img.shields.io/badge/semver-1.0.3.1-blue)
![CodeFactor Grade](https://img.shields.io/codefactor/grade/github/barrycarey/RedditRepostSleuth/master)

![Subreddit subscribers](https://img.shields.io/reddit/subreddit-subscribers/repostsleuthbot?style=social)
![Reddit User Karma](https://img.shields.io/reddit/user-karma/comment/repostsleuthbot?style=social)
![GitHub commit activity](https://img.shields.io/github/commit-activity/m/barrycarey/redditrepostsleuth)
![Discord](https://img.shields.io/discord/636038154951852042?style=plastic)

## About
Repost Sleuth Bot is a high performance bot that is able to detect Reddit reposts extremely fast.  

It also includes a large number of custom admin abilities to help moderators deal with reposts on their Subreddits

#### Supported Post Types

- **Images:** Fully Supported
- **Links:** Fully Supported 
- **Videos:** Not Supported
- **Text:** Not Supported

Code has been written for videos and text.  However, they are far too resource demanding to make public. 


## General Features
- Realtime repost detection for ALL supported content submitted to Reddit
- Ability to monitor any post and notify you if someone reposts it 

## Admin Features
- Realtime repost detection
- Comment on reposts
- Customize search settings for your Subreddit (Limit by matching %, date, subreddit, author, etc)
- Define custom comment templates
- Automatically remove reposts
- Automatically report reposts with custom report templates
- Automatically lock reposts 
- Automatically sticky the bot's comment
- Automatically mark a post as OC
- Automatically lock the bot's comment
- Custom report dashboard and management on www.repostsleuth.com
- Discord notifications (coming soon)

#### Commands

**!repost watch** - Monitor this post and notify you if we see it posted somewhere else

**!repost unwatch** - Disable an active repost monitors for this post

## Technology

Repost Sleuth makes heavy use of Celery with a Redis backend.  Celery allows a large number of CPU bound tasks to be run in parallel with a number of benefits.  

All data is stored in a MySQL database and we use SQLAlchemy to interact with the data.

The bot is split into roughly 9 Docker containers with various instances. 

Hardware wise, the bot runs on a Dell r720 with 2x Xeon 2680v2 CPUs and 512gb of RAM. Storage is an all flash array consisting of 8 Samsung Evo 500gb SSDs in RAID 10.

It currently consumes around 70% of these resources. 

## Feature Suggestions
If you are interested in seeing a specific feature [please open a discussion thread](https://github.com/barrycarey/RedditRepostSleuth/discussions).

## Contributing 

I'm open to contributions however I'm still working out how to handle it.  The bot cannot be easily run locally and.  
If you feel you can contribute something, please include tests for any for any code you wish to submit. 


### reddit usage FAQ

#### Your Bot Sucks, It Said a Reposted Meme Was Unique
Memes are by far the hardest reposts to detect accurately. Many templates can produces the same exact hash even with different text in the meme. Due to this most other reposts bots don't work well on meme subs since they produce tons of false positives.

Repost Sleuth has an extra layer of processing for memes that weeds out most false positives. It does result in some false negatives but it's generally pretty accurate.

Using the report False Positive / False Negative in the bots signature helps me track it.

At the moment only ~3.5 percent of comments the bot leaves are reported as false negatives.

#### Your Bot Sucks, It Said my original meme was a repost. 
This is called a False Positive.  Repost Sleuth is good at avoiding most false positives by erring on the side of being too strict.  But they happen.  That's life.  Don't take it personally. We constantly monitor reports and tune the bot the best we can. 

#### The bot said it didn't find a match, but the closest match was the same one!
An image may look exactly the same to your eye, but the bot sees each individual pixel. Things like JPEG compression can result in a big change to pixels and as a result, a big change to the hashes the bot uses for comparison. So 2 images that look identical may have hashes that are only 80% similar. 

Depending on the specific subreddit, this difference may or may not meet the similarity threshold. 

There's nothing I can do about this with the current implementation of the bot. It's not perfect but it works pretty well.  If you find that horrific, don't use it. 

#### Why did it detect my meme as a respost when it's not?
While the bot correctly identifies memes with the same template and different text most of the time, it's not 100%.  Especially with newer meme templates. 

The bot continually learns meme templates.  The more it sees a template the more accurate it gets.  However, as new templates are used, it may trigger a false positive until that template has more circulation. 

#### How do I summon the bot?
Tag the user as a comment to an image post.  u/repostsleuthbot

#### Hey asshole, posting something to another sub isn't a repost
If you properly crosspost something the bot will ignore it. If you take an image and upload it to a new sub you get flagged.

#### How far back do you search?
All Reddit posts from 2018 forward are indexed

#### How does it search so many images so quickly?
It uses a binary tree search for similar image hashes.  This allows it to perform fast, accurate searches without checking each individual image

#### Can I use this bot on my sub?
Yes! Visit www.repostsleuth.com and signin with your Reddit account.  Click My Subreddits in the menu then click Add under the sub you wish to activate the bot on. 

#### Does it support other types of posts besides images?
Currently Images and Link posts are support.  This may change in the future however resource usage for videos and text is an issue. 

#### What kind of hardware does the bot run on? 
A Dell R720 with 512gb of RAM and dual Xeon E5 2680v2
