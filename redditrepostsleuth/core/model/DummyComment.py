from praw import Reddit


class DummyComment:
    def __init__(self, body: str, subreddit: str, submission_id: str):
        self.id = 'hz3pblg'
        self.body = body
        self.permalink = '/r/mock/bot/comment'
        self.submission_id = submission_id

        class DummySubmission:
            id = self.submission_id

        class DummySubreddit:
            def __init__(self, subreddit: str):
                self.display_name = subreddit

        self.submission = DummySubmission()
        self.subreddit = DummySubreddit(subreddit)