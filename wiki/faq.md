##Your Bot Sucks, It Said a Reposted Meme Was Unique
---
Memes are by far the hardest reposts to detect accurately. Many templates can produces the same exact hash even with different text in the meme. Due to this most other reposts bots don't work well on meme subs since they produce tons of false positives.

Repost Sleuth has an extra layer of processing for memes that weeds out most false positives. It does result in some false negatives but it's generally pretty accurate.

Using the report False Positive / False Negative in the bots signature helps me track it.

At the moment only ~3.5 percent of comments the bot leaves are reported as false negatives.

##Your Bot Sucks, It Said my original meme was a repost. 
---
See answer above. 

This is called a False Positive.  Repost Sleuth is good at avoiding most false positives by erring on the side of being too strict.  But they happen.  That's life.  Don't take it personally. We constantly monitor reports and tune the bot the best we can. 

## The bot said it didn't find a match, but the closest match was the same one!
---
An image may look exactly the same to your eye, but the bot sees each individual pixel. Things like JPEG compression can result in a big change to pixels and as a result, a big change to the hashes the bot uses for comparison. So 2 images that look identical may have hashes that are only 80% similar. 

Depending on the specific subreddit, this difference may or may not meet the similarity threshold. 

There's nothing I can do about this with the current implementation of the bot. It's not perfect but it works pretty well.  If you find the horrific, don't use it. 

##Why did it detect my meme as a respost when it's not?
---
While the bot correctly identifies memes with the same template and different text most of the time, it's not 100%.  Especially with newer meme templates. 

The bot continually learns meme templates.  The more it sees a template the more accurate it gets.  However, as new templates are used, it may trigger a false positive until that template has more circulation. 

##How do I summon the bot?
---
Tag the user as a comment to an image post.  u/repostsleuthbot

##I summoned the bot but it never responded
---
The bot is still 'Beta'.  I'm continually working on stuff and it might crash from time to time. It will be a couple weeks before it's completely stable. 

##Hey asshole, posting something to another sub isn't a repost
---
If you properly crosspost something the bot will ignore it. If you take an image and upload it to a new sub you're getting flagged

##How far back do you search?
---
We're working on indexing older posts.  We are currently back to March 2018. Depending on storage space we may go back another year or 2. 

##How does it search so many images so quickly?
---
It uses a binary tree search for similar image hashes.  This allows it to perform fast, accurate searches without checking each individual image

##Can I use this bot on my sub?
---
Yes! We're currently looking for communities to Beta test this feature.  Enabled communities will have realtime checking of all new posts with configurable options. Send a PM u/barrycarey

##Does it support other types of posts besides images?
---
Not yet.  However, we will be support all post types in the future. We want to focus on images first and get it right.

##What kind of hardware does the bot run on? 
---
Currently the bot is running on 3 machines. A Dell r710 server with 2x Xeon X5670 12 core CPUs w/ 96gb RAM, a Ryzen 2700x w/ 32gb RAM, an i7 3770k w/ 32gb of RAM. All of these systems are running Docker containers to deal with the different pieces of the bot. 

Once we finish populating our database most of this hardware will not be required.  At that point the plan is to move most everything into the cloud.