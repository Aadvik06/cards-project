class OptimizerError(ValueError):
    """Base error for request or rule failures."""


class NotFoundError(OptimizerError):
    """Raised when an object cannot be found."""


class InvalidDecisionError(OptimizerError):
    """Raised when a recommendation decision is incomplete."""

