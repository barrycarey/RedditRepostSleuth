from unittest import TestCase

from redditrepostsleuth.summonssvc.commandparsing.command_parser import CommandParser


class TestCommandParser(TestCase):
    def test_parse_repost_cmd(self):
        parser = CommandParser()
        r = parser.parse_repost_cmd('test -meme -strict tight')
        self.assertTrue(r.meme_filter)
        self.assertEqual(r.strictness, 'tight')
        self.assertFalse(r.same_sub)

    def test_parse_watch_command(self):
        self.fail()

    def test_parse_root_command(self):
        self.fail()
