"""Failures a source can show to the user."""


class SourceError(RuntimeError):
    """An actionable connector failure safe to display without secret values."""


class NotConnectedError(SourceError):
    """An optional connection was never set up; shown as a neutral state, not a failure."""


class SignInRequired(SourceError):
    """The saved sign-in is missing or no longer accepted; a browser sign-in would fix it."""
