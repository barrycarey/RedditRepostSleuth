from praw import Reddit


class DummyComment:
    def __init__(self, body: str):
        self.id = 'hz3pblg'
        self.body = body
        self.permalink = '/r/mock/bot/comment'

        class DummySubmission:
            id = 't5aqms'

        class DummySubreddit:
            display_name = 'memes'

        self.submission = DummySubmission()
        self.subreddit = DummySubreddit()