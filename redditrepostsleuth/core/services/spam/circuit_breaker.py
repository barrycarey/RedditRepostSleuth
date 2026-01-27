"""Circuit breaker for Reddit API reliability.

Implements the circuit breaker pattern to protect against cascading failures
when the Reddit API is unavailable or experiencing issues.
"""
import logging
from datetime import datetime
from enum import Enum
from typing import Callable, Optional, TypeVar

log = logging.getLogger(__name__)

T = TypeVar('T')


class CircuitState(Enum):
    """States for the circuit breaker."""
    CLOSED = 'CLOSED'       # Normal operation - all requests allowed
    OPEN = 'OPEN'           # API failing - reject all requests
    HALF_OPEN = 'HALF_OPEN'  # Testing recovery - allow limited requests


class CircuitBreakerOpen(Exception):
    """Raised when circuit breaker is open and calls are rejected."""

    def __init__(self, message: str, retry_after: int = 0):
        super().__init__(message)
        self.retry_after = retry_after


class CircuitBreaker:
    """
    Circuit breaker pattern for Reddit API calls.

    Protects against cascading failures by failing fast and degrading gracefully.

    State Transitions:
        CLOSED -> OPEN: When consecutive failures reach failure_threshold
        OPEN -> HALF_OPEN: After recovery_timeout seconds
        HALF_OPEN -> CLOSED: After success_threshold successful calls
        HALF_OPEN -> OPEN: On any failure (with increased timeout)
    """

    def __init__(
        self,
        failure_threshold: int = 5,
        success_threshold: int = 2,
        recovery_timeout: int = 60,
        backoff_multiplier: float = 1.5,
        max_recovery_timeout: int = 600
    ):
        """
        Initialize the circuit breaker.

        Args:
            failure_threshold: Number of consecutive failures before opening circuit
            success_threshold: Number of successes in HALF_OPEN before closing
            recovery_timeout: Seconds to wait before attempting recovery
            backoff_multiplier: Multiply timeout on repeated failures
            max_recovery_timeout: Maximum recovery timeout in seconds
        """
        self.failure_threshold = failure_threshold
        self.success_threshold = success_threshold
        self.recovery_timeout = recovery_timeout
        self.backoff_multiplier = backoff_multiplier
        self.max_recovery_timeout = max_recovery_timeout

        # Current recovery timeout (can be increased by backoff)
        self._current_recovery_timeout = recovery_timeout

        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time: Optional[datetime] = None
        self._opening_time: Optional[datetime] = None

    @property
    def state(self) -> CircuitState:
        """Get current circuit state."""
        return self._state

    @property
    def is_closed(self) -> bool:
        """Check if circuit is closed (normal operation)."""
        return self._state == CircuitState.CLOSED

    @property
    def is_open(self) -> bool:
        """Check if circuit is open (rejecting calls)."""
        return self._state == CircuitState.OPEN

    @property
    def is_half_open(self) -> bool:
        """Check if circuit is half-open (testing recovery)."""
        return self._state == CircuitState.HALF_OPEN

    def call(self, func: Callable[..., T], *args, **kwargs) -> T:
        """
        Execute function through circuit breaker.

        Args:
            func: Function to call
            *args: Function arguments
            **kwargs: Function keyword arguments

        Returns:
            Function result

        Raises:
            CircuitBreakerOpen: If circuit is open
            Exception: Re-raises any exception from the function
        """
        if self._state == CircuitState.OPEN:
            if self._should_attempt_reset():
                self._transition_to_half_open()
            else:
                raise CircuitBreakerOpen(
                    f"Circuit breaker is OPEN. Retry after {self._time_until_retry()}s",
                    retry_after=self._time_until_retry()
                )

        try:
            result = func(*args, **kwargs)
            self._on_success()
            return result
        except Exception as e:
            self._on_failure(e)
            raise

    def record_success(self) -> None:
        """Manually record a successful call."""
        self._on_success()

    def record_failure(self, exception: Optional[Exception] = None) -> None:
        """Manually record a failed call."""
        self._on_failure(exception)

    def reset(self) -> None:
        """Reset the circuit breaker to initial state."""
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time = None
        self._opening_time = None
        self._current_recovery_timeout = self.recovery_timeout
        log.info("Circuit breaker reset to CLOSED state")

    def _on_success(self) -> None:
        """Handle successful call."""
        self._failure_count = 0
        self._last_failure_time = None

        if self._state == CircuitState.HALF_OPEN:
            self._success_count += 1
            if self._success_count >= self.success_threshold:
                self._transition_to_closed()
        else:
            self._success_count = 0

    def _on_failure(self, exception: Optional[Exception] = None) -> None:
        """Handle failed call."""
        self._failure_count += 1
        self._success_count = 0
        self._last_failure_time = datetime.utcnow()

        if self._state == CircuitState.HALF_OPEN:
            # Any failure in HALF_OPEN triggers OPEN with increased timeout
            self._current_recovery_timeout = min(
                int(self._current_recovery_timeout * self.backoff_multiplier),
                self.max_recovery_timeout
            )
            self._transition_to_open()
            log.warning(
                f"Circuit breaker OPEN - recovery timeout increased to "
                f"{self._current_recovery_timeout}s after failure: {exception}"
            )
        elif self._failure_count >= self.failure_threshold:
            self._transition_to_open()
            log.warning(
                f"Circuit breaker OPEN after {self._failure_count} consecutive "
                f"failures. Last error: {exception}"
            )

    def _transition_to_open(self) -> None:
        """Transition to OPEN state."""
        self._state = CircuitState.OPEN
        self._opening_time = datetime.utcnow()

    def _transition_to_half_open(self) -> None:
        """Transition to HALF_OPEN state."""
        self._state = CircuitState.HALF_OPEN
        self._success_count = 0
        log.info("Circuit breaker entering HALF_OPEN state")

    def _transition_to_closed(self) -> None:
        """Transition to CLOSED state."""
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._opening_time = None
        # Reset recovery timeout on successful recovery
        self._current_recovery_timeout = self.recovery_timeout
        log.info("Circuit breaker CLOSED - API recovered")

    def _should_attempt_reset(self) -> bool:
        """Check if enough time has passed to attempt recovery."""
        if self._opening_time is None:
            return True
        elapsed = (datetime.utcnow() - self._opening_time).total_seconds()
        return elapsed >= self._current_recovery_timeout

    def _time_until_retry(self) -> int:
        """Calculate seconds until retry is allowed."""
        if self._opening_time is None:
            return 0
        elapsed = (datetime.utcnow() - self._opening_time).total_seconds()
        return max(0, int(self._current_recovery_timeout - elapsed))

    def get_status(self) -> dict:
        """Get current circuit breaker status for monitoring."""
        return {
            'state': self._state.value,
            'failure_count': self._failure_count,
            'success_count': self._success_count,
            'recovery_timeout': self._current_recovery_timeout,
            'time_until_retry': self._time_until_retry() if self.is_open else 0,
            'last_failure_time': (
                self._last_failure_time.isoformat()
                if self._last_failure_time else None
            ),
        }
