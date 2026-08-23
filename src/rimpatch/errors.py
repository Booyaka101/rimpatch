"""User-facing errors. Anything raised as RimpatchError is printed as a message, not a traceback."""

from __future__ import annotations


class RimpatchError(Exception):
    """A problem the user can fix: a bad path, an unreadable file, a missing game install."""


class GameDataNotFound(RimpatchError):
    pass


class NoModsFound(RimpatchError):
    pass
