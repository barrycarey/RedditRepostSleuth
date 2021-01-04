from unittest import TestCase

from redditrepostsleuth.core.config import Config
from redditrepostsleuth.core.exception import InvalidCommandException
from redditrepostsleuth.core.model.commands.repost_link_cmd import RepostLinkCmd
from redditrepostsleuth.core.model.commands.watch_cmd import WatchCmd
from redditrepostsleuth.summonssvc.commandparsing.command_parser import CommandParser


class TestCommandParser(TestCase):

    def test_parse_root_command__valid_command(self):
        parser = CommandParser(config=Config(redis_host='dummy'))
        r = parser.parse_root_command('repost -meme -matching tight')
        self.assertEqual('repost', r)

    def test_parse_root_command__invalid_command(self):
        parser = CommandParser(config=Config(redis_host='dummy'))
        self.assertRaises(InvalidCommandException, parser.parse_root_command, 'junk -meme -matching tight')

