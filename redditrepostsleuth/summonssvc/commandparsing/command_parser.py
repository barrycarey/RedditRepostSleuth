from typing import Text

from redditrepostsleuth.core.config import Config
from redditrepostsleuth.core.logging import log
from redditrepostsleuth.summonssvc.commandparsing.argumentparserthrow import ArgumentParserThrow


class CommandParser:
    def __init__(self, config: Config = None):
        if config:
            self.config = config
        else:
            self.config = Config()

    def parse_watch_command(self, cmd: Text):
        pass

    def parse_root_command(self, command: str):
        if not command:
            log.error('Got empty command.  Returning repost')
            return 'repost'
        parser = ArgumentParserThrow()
        parser.add_argument('command', default=None, choices=['repost', 'watch', 'unwatch'])
        options, args = parser.parse_known_args(command.split(' '))
        return options.command

    def _get_hamming_from_strictness(self, strictness: Text) -> int:
        if strictness is None:
            return

        if strictness == 'loose':
            # TODO - What happens if this isn't set in config?
            return self.config.summons_match_strictness_loose
        elif strictness == 'tight':
            return self.config.summons_match_strictness_tight
        else:
            return self.config.default_hamming_distance
