from praw import Reddit

from redditrepostsleuth.core.logging import log


class RedditManager:
    """
    Wrapper to 'cache' comments and submissions
    """
    def __init__(self, reddit: Reddit):
        self.reddit = reddit
        self._comments = []
        self._submissions = []
        self._subreddits = []

    def subreddit(self, sub_name: str):
        return self._return_subreddit(sub_name)

    def _return_subreddit(self, sub_name: str):
        for sub in self._subreddits:
            if sub.display_name == sub_name:
                log.debug('Returning cached sub %s', sub_name)
                return sub
        new_sub = self.reddit.subreddit(sub_name)
        if new_sub:
            log.debug('Returning new subreddit %s', sub_name)
            self._subreddits.append(new_sub)
            return new_sub

    def comment(self, comment_id: str):
        return self._return_comment(comment_id)

    def _return_comment(self, comment_id: str):
        for comment in self._comments:
            if comment.id == comment_id:
                log.debug('Returning cached comment %s', comment_id)
                return comment
        new_comment = self.reddit.comment(comment_id)
        log.debug('Returning new comment %s', comment_id)
        if new_comment:
            self._comments.append(new_comment)
            return new_comment

    def submission(self, submission_id: str):
        return self._return_submission(submission_id)

    def _return_submission(self, submission_id: str):
        for submission in self._submissions:
            if submission.id == submission_id:
                log.debug('Returning cached submission %s', submission_id)
                return submission
        new_submission = self.reddit.submission(submission_id)
        if new_submission:
            self._submissions.append(new_submission)
            log.debug('Returning new submission %s', submission_id)
            return new_submission