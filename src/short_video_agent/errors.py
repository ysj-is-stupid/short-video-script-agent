"""Application-specific error types."""

from __future__ import annotations


class AppError(Exception):
    """Base error carrying a stable machine-readable code."""

    def __init__(
        self,
        *,
        code: str,
        message: str,
        retryable: bool = False,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable


class ConfigurationError(AppError):
    """Raised when environment-backed configuration is invalid."""


class ModelAdapterError(AppError):
    """Raised when a model adapter cannot return a valid decision."""


class ModelOutputValidationError(AppError):
    """Raised when returned model content is not a valid AgentDecision."""


class ToolExecutionError(AppError):
    """Raised by tool infrastructure before conversion to a ToolResult."""

