from praw import Reddit


class RedditManager:
    """
    Wrapper to 'cache' comments and submissions
    """
    def __init__(self, reddit: Reddit):
        self.reddit = reddit
        self.comments = []
        self.submissions = []
        self.subreddits = []

    def comment(self, comment_id: str):
        return self._return_comment(comment_id)

    def _return_comment(self, comment_id: str):
        for comment in self.comments:
            if comment.id == comment_id:
                return comment
            new_comment = self.reddit.comment(comment_id)
            if new_comment:
                self.comments.append(new_comment)
                return new_comment

    def submission(self, submission_id: str):
        return self._return_comment(submission_id)

    def _return_submission(self, submission_id: str):
        for submission in self.submissions:
            if submission.id == submission_id:
                return submission
            new_submission = self.reddit.comment(submission_id)
            if new_submission:
                self.submissions.append(new_submission)
                return new_submission