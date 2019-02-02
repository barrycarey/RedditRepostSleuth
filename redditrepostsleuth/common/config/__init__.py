import os

import praw

print(os.getcwd())
reddit = praw.Reddit(user_agent='RepostSleuthBot')