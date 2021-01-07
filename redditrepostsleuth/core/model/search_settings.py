
from typing import Optional


class SearchSettings:
    """
    Wrapper that contains all settings to be used when searching for a repost
    Initial values will be set to sensible defaults if none are provided
    """
    def __init__(
            self,
            target_title_match: Optional[int] = None,
            max_matches: int = 75,
            same_sub: bool = False,
            max_days_old: Optional[int] = None,
            filter_dead_matches: bool = False,
            filter_removed_matches: bool = False,
            only_older_matches: bool = True,
            filter_same_author: bool = True,
            filter_crossposts: bool = True
    ):
        """

        :param target_title_match: Threshold a title must meet to be considered a match
        :param max_matches: Max matches to fetch from search
        :param same_sub: Only keep matches from same subreddit
        :param max_days_old: Drop all matches older than X days
        :param filter_dead_matches: Remove matches that return a 404
        :param filter_removed_matches: Removed matches that have been removed from Reddit
        :param only_older_matches:  Only include matches older than the searched post
        :param filter_same_author: Remove matches by the same author is searched post
        """
        self.filter_crossposts = filter_crossposts
        self.filter_same_author = filter_same_author
        self.only_older_matches = only_older_matches
        self.filter_removed_matches = filter_removed_matches
        self.filter_dead_matches = filter_dead_matches
        self.max_days_old = max_days_old
        self.same_sub = same_sub
        self.max_matches = max_matches
        self.target_title_match = target_title_match

    @property
    def search_scope(self):
        return 'This Sub' if self.same_sub else 'Reddit'

    @property
    def check_title(self):
        return self.target_title_match is None

    def __repr__(self):
        r = ''
        for k, v in self.__dict__.items():
            r += f'{k}: {v} | '
        return r

    def to_dict(self):
        return {
            'filter_crossposts': self.filter_crossposts,
            'filter_same_author': self.filter_same_author,
            'only_older_matches': self.only_older_matches,
            'filter_removed_matches': self.filter_removed_matches,
            'filter_dead_matches': self.filter_dead_matches,
            'max_days_old': self.max_days_old,
            'same_sub': self.same_sub,
            'max_matches': self.max_matches,
            'target_title_match': self.target_title_match,
            'search_scope': self.search_scope,
            'check_title': self.check_title
        }