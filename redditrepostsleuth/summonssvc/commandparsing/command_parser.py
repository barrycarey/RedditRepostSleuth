from typing import Text

from redditrepostsleuth.core.model.commands.repost_image_cmd import RepostImageCmd
from redditrepostsleuth.summonssvc.commandparsing.argumentparserthrow import ArgumentParserThrow

class CommandParser:

    def __init__(self):
        pass

    def parse_repost_cmd(self, cmd: str):
        parser = ArgumentParserThrow(cmd)
        parser.add_argument('command', default=None)
        parser.add_argument('-meme', default=True, dest='meme_filter', help="Enable the meme filter", action='store_true')
        parser.add_argument('-samesub', default=False, dest='same_sub', help="Only search this sub",
                            action='store_true')
        parser.add_argument('-strict', choices=['loose', 'regular', 'tight'], default='regular', dest='strictness', help='High strict should matches be')
        args = parser.parse_args(cmd.split(' '))
        return RepostImageCmd(
            meme_filter=args.meme_filter,
            strictness=args.strictness,
            same_sub=args.same_sub
        )

    def parse_watch_command(self, cmd: Text):
        pass

    def parse_root_command(self, command: str):
        parser = ArgumentParserThrow()
        parser.add_argument('command', default=None, choices=['repost', 'watch'])
        args = parser.parse_known_args(command.split(' '))
        return args.command

if __name__ == '__main__':
    parser = CommandParser()
    r = parser.parse_repost_cmd('test -meme -strict tight')
    print('')