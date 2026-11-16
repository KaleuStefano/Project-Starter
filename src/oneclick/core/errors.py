"""Exceptions raised by the core. Every message is written for the end user."""


class OneClickError(Exception):
    """Base class. ``str(error)`` is safe to show in a dialog."""


class InvalidPatternError(OneClickError):
    """The naming pattern is not valid."""


class InvalidNameError(OneClickError):
    """The project name (or the final folder name) cannot be used."""


class DestinationError(OneClickError):
    """The destination folder is missing or not writable."""


class TemplateError(OneClickError):
    """A template is invalid, missing or too large."""


class ProjectExistsError(OneClickError):
    """A folder with the target name already exists."""


class CreateError(OneClickError):
    """Creating the project failed (partial work is rolled back)."""


class UndoError(OneClickError):
    """The last project cannot be undone safely."""
