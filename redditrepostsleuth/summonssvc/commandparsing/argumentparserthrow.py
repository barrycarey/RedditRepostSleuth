from argparse import ArgumentParser
from typing import Text, NoReturn

from redditrepostsleuth.core.exception import InvalidCommandException


class ArgumentParserThrow(ArgumentParser):
    def error(self, message: Text) -> NoReturn:
        raise InvalidCommandException(message)
