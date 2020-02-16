from unittest import TestCase

from redditrepostsleuth.core.config import Config
from redditrepostsleuth.core.exception import InvalidCommandException
from redditrepostsleuth.core.model.commands.repost_link_cmd import RepostLinkCmd
from redditrepostsleuth.core.model.commands.watch_cmd import WatchCmd
from redditrepostsleuth.summonssvc.commandparsing.command_parser import CommandParser


class TestCommandParser(TestCase):
    def test_parse_repost_cmd(self):
        parser = CommandParser(config=Config(summons_match_strictness_tight=9))
        r = parser.parse_repost_image_cmd('-meme -matching tight')
        self.assertTrue(r.meme_filter)
        self.assertEqual(r.strictness, 9)
        self.assertFalse(r.same_sub)

    def test_parse_root_command__valid_command(self):
        parser = CommandParser(config=Config(redis_host='dummy'))
        r = parser.parse_root_command('repost -meme -matching tight')
        self.assertEqual('repost', r)

    def test_parse_root_command__invalid_command(self):
        parser = CommandParser(config=Config(redis_host='dummy'))
        self.assertRaises(InvalidCommandException, parser.parse_root_command, 'junk -meme -matching tight')

    def test_parse_repost_link_cmd_no_params_return_default_cmd(self):
        parser = CommandParser(config=Config(redis_host='dummy'))
        r = parser.parse_repost_link_cmd('')
        self.assertEqual(RepostLinkCmd, type(r))

    def test_parse_repost_link_cmd_invalid_params(self):
        parser = CommandParser(config=Config(redis_host='dummy'))
        r = parser.parse_repost_link_cmd('-meme')
        self.assertEqual(RepostLinkCmd, type(r))
        self.assertFalse(r.same_sub)

    def test_parse_watch_cmd_no_params_return_default_cmd(self):
        parser = CommandParser(config=Config(redis_host='dummy'))
        r = parser.parse_watch_cmd('')
        self.assertEqual(WatchCmd, type(r))
        self.assertFalse(r.same_sub)

    def test_parse_watch_cmd_invalid_params(self):
        parser = CommandParser(config=Config(redis_host='dummy'))
        r = parser.parse_watch_cmd('-meme')
        self.assertEqual(WatchCmd, type(r))
        self.assertFalse(r.same_sub)

    def test_parse_watch_cmd_with_params_return_configured_cmd(self):
        parser = CommandParser(config=Config(redis_host='dummy'))
        r = parser.parse_watch_cmd('-samesub -expire 10')
        self.assertEqual(WatchCmd, type(r))
        self.assertTrue(r.same_sub)
        self.assertEqual(r.expire, 10)