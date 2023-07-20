from praw import Reddit


class DummyComment:
    def __init__(self, body: str, subreddit: str):
        self.id = 'hz3pblg'
        self.body = body
        self.permalink = '/r/mock/bot/comment'

        class DummySubmission:
            id = 't5aqms'

        class DummySubreddit:
            def __init__(self, subreddit: str):
                self.display_name = subreddit

        self.submission = DummySubmission()
        self.subreddit = DummySubreddit(subreddit)