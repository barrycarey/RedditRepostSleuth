from typing import Text

from redditrepostsleuth.core.config import Config
from redditrepostsleuth.core.model.commands.repost_image_cmd import RepostImageCmd
from redditrepostsleuth.summonssvc.commandparsing.argumentparserthrow import ArgumentParserThrow

class CommandParser:

    def __init__(self, config: Config=None):
        if config:
            self.config = config
        else:
            self.config = Config()

    def parse_repost_cmd(self, cmd: str):
        parser = ArgumentParserThrow(cmd)
        parser.add_argument('command', default=None)
        parser.add_argument('-meme', default=True, dest='meme_filter', help="Enable the meme filter", action='store_true')
        parser.add_argument('-all', default=True, dest='all_matches', help="Provide all matches in list format",
                            action='store_true')
        parser.add_argument('-samesub', default=False, dest='same_sub', help="Only search this sub",
                            action='store_true')
        parser.add_argument('-strict', choices=['loose', 'regular', 'tight'], default='regular', dest='strictness', help='High strict should matches be')
        args = parser.parse_args(cmd.split(' '))
        return RepostImageCmd(
            meme_filter=args.meme_filter,
            strictness=self._get_hamming_from_strictness(args.strictness),
            same_sub=args.same_sub,
            all_matches=args.all_matches
        )

    def parse_watch_command(self, cmd: Text):
        pass

    def parse_root_command(self, command: str):
        parser = ArgumentParserThrow()
        parser.add_argument('command', default=None, choices=['repost', 'watch'])
        args = parser.parse_known_args(command.split(' '))
        return args.command

    def _get_hamming_from_strictness(self, strictness: Text) -> int:
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