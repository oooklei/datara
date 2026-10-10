from master.retry_classifier import classify_error, retry_decision


def test_classifies_failure_kinds():
    assert classify_error("TimeoutError", "upstream timed out", None) == "transient"
    assert classify_error("HttpError", "rate limit exceeded", 429) == "congestion"
    assert classify_error("ValueError", "invalid mapping syntax", 2) == "deterministic"
    assert classify_error("VendorError", "unexpected provider response", 1) == "external"


def test_retry_decision_uses_safe_backoff_and_rejects_deterministic_errors():
    assert retry_decision("transient", 1, 60).delay_seconds == 1
    assert retry_decision("transient", 2, 60).delay_seconds == 5
    assert retry_decision("transient", 3, 60).delay_seconds == 25
    assert retry_decision("congestion", 1, 5).delay_seconds == 30
    assert retry_decision("external", 1, 12).delay_seconds == 12
    assert not retry_decision("deterministic", 1, 12).retryable
