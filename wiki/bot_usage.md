### Using the bot
To have the bot perform a repost check simply tag the bot in a comment. u/repostsleuthbot

### Commands
The bot has several commands available to modify the search results.  These can be used in any combination.

The basic format is

```u/repostsleuthbot -age 60 -samesub```

### Base Commands

#### Image Post Commands

* -all | Send you a PM with all matches
* -meme | Use the meme filter during the search
* -samesub | Only search within the same Subreddit
* -matching [loose, regular, tight] | Changes how strict the matching threshold is
* -age [days] | Only find matches within this number of days

#### Link Post Commands

* -all | Send you a PM with all matches
* -samesub | Only search within the same Subreddit
* -age [days] | Only find matches within this number of days

**Examples:**

*Seach for matches no more than 60 days old in this sub*

```u/repostsleuthbot -age 60 -samesub```

*Find all matches using a strict matching threshold*

```u/repostsleuthbot -matching strict -all```