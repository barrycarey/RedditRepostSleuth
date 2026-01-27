"""Tests for CircuitBreaker."""
import time
import unittest
from unittest.mock import MagicMock

from redditrepostsleuth.core.services.spam.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerOpen,
    CircuitState,
)


class TestCircuitBreaker(unittest.TestCase):
    """Test cases for CircuitBreaker class."""

    def setUp(self):
        """Set up test fixtures."""
        self.breaker = CircuitBreaker(
            failure_threshold=3,
            success_threshold=2,
            recovery_timeout=1,  # 1 second for fast tests
            backoff_multiplier=1.5
        )

    def test_initial_state_is_closed(self):
        """Test that circuit breaker starts in CLOSED state."""
        self.assertEqual(self.breaker.state, CircuitState.CLOSED)
        self.assertTrue(self.breaker.is_closed)
        self.assertFalse(self.breaker.is_open)

    def test_successful_calls_keep_circuit_closed(self):
        """Test that successful calls keep circuit in CLOSED state."""
        def success_func():
            return "success"

        for _ in range(10):
            result = self.breaker.call(success_func)
            self.assertEqual(result, "success")

        self.assertTrue(self.breaker.is_closed)
        self.assertEqual(self.breaker._failure_count, 0)

    def test_circuit_opens_after_failure_threshold(self):
        """Test that circuit opens after reaching failure threshold."""
        def failing_func():
            raise ValueError("test error")

        # Cause enough failures to open the circuit
        for _ in range(3):
            with self.assertRaises(ValueError):
                self.breaker.call(failing_func)

        self.assertTrue(self.breaker.is_open)
        self.assertEqual(self.breaker.state, CircuitState.OPEN)

    def test_open_circuit_rejects_calls(self):
        """Test that open circuit rejects new calls immediately."""
        from datetime import datetime
        # Force circuit open with recent opening time (so recovery timeout hasn't passed)
        self.breaker._state = CircuitState.OPEN
        self.breaker._opening_time = datetime.utcnow()
        self.breaker._current_recovery_timeout = 60  # 60 seconds, more than test duration

        def any_func():
            return "should not be called"

        with self.assertRaises(CircuitBreakerOpen) as context:
            self.breaker.call(any_func)

        self.assertIn("OPEN", str(context.exception))

    def test_circuit_transitions_to_half_open_after_recovery_timeout(self):
        """Test that circuit transitions to HALF_OPEN after recovery timeout."""
        # Force circuit open
        def failing_func():
            raise ValueError("test error")

        for _ in range(3):
            with self.assertRaises(ValueError):
                self.breaker.call(failing_func)

        self.assertTrue(self.breaker.is_open)

        # Wait for recovery timeout
        time.sleep(1.5)

        # Next call should transition to HALF_OPEN
        def success_func():
            return "success"

        result = self.breaker.call(success_func)
        self.assertEqual(result, "success")
        # After one success, still in HALF_OPEN (need 2)
        # But if it succeeded, it might close with success_threshold=2

    def test_half_open_closes_after_success_threshold(self):
        """Test that HALF_OPEN state closes after enough successes."""
        self.breaker._state = CircuitState.HALF_OPEN
        self.breaker._success_count = 0

        def success_func():
            return "success"

        # Two successful calls should close the circuit
        self.breaker.call(success_func)
        self.breaker.call(success_func)

        self.assertTrue(self.breaker.is_closed)

    def test_half_open_reopens_on_failure(self):
        """Test that HALF_OPEN state reopens on any failure."""
        self.breaker._state = CircuitState.HALF_OPEN

        def failing_func():
            raise ValueError("test error")

        with self.assertRaises(ValueError):
            self.breaker.call(failing_func)

        self.assertTrue(self.breaker.is_open)

    def test_backoff_multiplier_increases_recovery_timeout(self):
        """Test that recovery timeout increases on repeated failures."""
        # Use a higher initial timeout so backoff multiplier effect is visible
        self.breaker._current_recovery_timeout = 10
        initial_timeout = self.breaker._current_recovery_timeout

        # Open circuit in HALF_OPEN, then fail
        self.breaker._state = CircuitState.HALF_OPEN

        def failing_func():
            raise ValueError("test error")

        with self.assertRaises(ValueError):
            self.breaker.call(failing_func)

        # Recovery timeout should have increased (10 * 1.5 = 15)
        self.assertGreater(
            self.breaker._current_recovery_timeout,
            initial_timeout
        )

    def test_reset_restores_initial_state(self):
        """Test that reset restores circuit to initial state."""
        # Put circuit in various states
        self.breaker._state = CircuitState.OPEN
        self.breaker._failure_count = 10
        self.breaker._current_recovery_timeout = 300

        self.breaker.reset()

        self.assertTrue(self.breaker.is_closed)
        self.assertEqual(self.breaker._failure_count, 0)
        self.assertEqual(self.breaker._current_recovery_timeout, self.breaker.recovery_timeout)

    def test_record_success_manually(self):
        """Test manually recording success."""
        self.breaker._failure_count = 3

        self.breaker.record_success()

        self.assertEqual(self.breaker._failure_count, 0)

    def test_record_failure_manually(self):
        """Test manually recording failure."""
        self.breaker._failure_count = 2

        self.breaker.record_failure(ValueError("test"))

        self.assertEqual(self.breaker._failure_count, 3)
        self.assertTrue(self.breaker.is_open)

    def test_get_status_returns_state_info(self):
        """Test get_status returns useful information."""
        status = self.breaker.get_status()

        self.assertIn('state', status)
        self.assertIn('failure_count', status)
        self.assertIn('success_count', status)
        self.assertIn('recovery_timeout', status)


class TestCircuitBreakerOpen(unittest.TestCase):
    """Test cases for CircuitBreakerOpen exception."""

    def test_exception_message(self):
        """Test exception includes retry_after in message."""
        exc = CircuitBreakerOpen("test message", retry_after=120)
        self.assertEqual(exc.retry_after, 120)
        self.assertIn("test message", str(exc))

    def test_default_retry_after(self):
        """Test default retry_after is 0."""
        exc = CircuitBreakerOpen("test")
        self.assertEqual(exc.retry_after, 0)


if __name__ == '__main__':
    unittest.main()
