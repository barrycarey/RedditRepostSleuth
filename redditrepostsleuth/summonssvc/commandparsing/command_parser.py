from typing import Text

from redditrepostsleuth.core.config import Config
from redditrepostsleuth.core.exception import InvalidCommandException
from redditrepostsleuth.core.logging import log
from redditrepostsleuth.core.model.commands.repost_image_cmd import RepostImageCmd
from redditrepostsleuth.core.model.commands.repost_link_cmd import RepostLinkCmd
from redditrepostsleuth.summonssvc.commandparsing.argumentparserthrow import ArgumentParserThrow

class CommandParser:

    def __init__(self, config: Config=None):
        if config:
            self.config = config
        else:
            self.config = Config()

    def parse_repost_image_cmd(self, cmd: str) -> RepostImageCmd:
        parser = ArgumentParserThrow(cmd)
        parser.add_argument('command', default=None)
        parser.add_argument('-meme', default=self.config.summons_meme_filter, dest='meme_filter', help="Enable the meme filter", action='store_true')
        parser.add_argument('-all', default=self.config.summons_all_matches, dest='all_matches', help="Provide all matches in list format",
                            action='store_true')
        parser.add_argument('-samesub', default=self.config.summons_same_sub, dest='same_sub', help="Only search this sub",
                            action='store_true')
        parser.add_argument('-matching', choices=['loose', 'regular', 'tight'], default=None, dest='strictness', help='High strict should matches be')
        parser.add_argument('-age', type=int, default=self.config.summons_max_age, dest='age',
                            help='High strict should matches be')
        try:
            args = parser.parse_args(cmd.split(' '))
        except InvalidCommandException as e:
            log.exception('Invalid command error: %s', e)
            return self.get_default_repost_image_cmd()

        return RepostImageCmd(
            meme_filter=args.meme_filter,
            strictness=self._get_hamming_from_strictness(args.strictness),
            same_sub=args.same_sub,
            all_matches=args.all_matches,
            match_age=args.age
        )

    def parse_repost_link_cmd(self, cmd: Text) -> RepostLinkCmd:
        parser = ArgumentParserThrow(cmd)
        parser.add_argument('command', default=None)
        parser.add_argument('-all', default=self.config.summons_all_matches, dest='all_matches',
                            help="Provide all matches in list format",
                            action='store_true')
        parser.add_argument('-samesub', default=self.config.summons_same_sub, dest='same_sub',
                            help="Only search this sub",
                            action='store_true')
        parser.add_argument('-age', type=int, default=self.config.summons_max_age, dest='age',
                            help='High strict should matches be')
        try:
            args = parser.parse_args(cmd.split(' '))
        except InvalidCommandException as e:
            log.exception('Invalid command error: %s', e)
            return self.get_default_repost_link_cmd()

        return RepostLinkCmd(
            same_sub=args.same_sub,
            all_matches=args.all_matches,
            match_age=args.age
        )

    def get_default_repost_image_cmd(self):
        return RepostImageCmd(
            meme_filter=self.config.summons_meme_filter,
            strictness=None,
            same_sub=self.config.summons_same_sub,
            all_matches=self.config.summons_all_matches,
            match_age=self.config.summons_max_age
        )

    def get_default_repost_link_cmd(self):
        return RepostLinkCmd(
            same_sub=self.config.summons_same_sub,
            all_matches=self.config.summons_all_matches,
            match_age=self.config.summons_max_age
        )

    def parse_watch_command(self, cmd: Text):
        pass

    def parse_root_command(self, command: str):
        parser = ArgumentParserThrow()
        parser.add_argument('command', default=None, choices=['repost', 'watch'])
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

if __name__ == '__main__':
    parser = CommandParser()
    r = parser.parse_root_command('feel like i’ve seen this before but i just wanna check')
    print('')