#!/usr/bin/env python3
"""Unit test for the THETA credential hardening (calibration_tracker.assert_theta_ready / get_theta_client).
Blank/whitespace creds must raise ThetaUnavailable with the greppable CALIBRATION_THETA_DOWN token,
BEFORE any network call. The _fetch_impl test-injection must bypass the real smoke call. No real Theta.

Usage: python backend/test_theta_hardening.py
"""
import os
import sys

# Force blank creds BEFORE importing so load_dotenv (override=False) can't backfill real values.
os.environ["THETA_EMAIL"] = ""
os.environ["THETA_PASSWORD"] = ""

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import calibration_tracker as CT  # noqa: E402


def main():
    failures = []

    def check(name, cond):
        if not cond:
            failures.append(name)

    # 1. get_theta_client rejects blank creds with the distinct ThetaUnavailable type.
    try:
        CT.get_theta_client()
        check("get_theta_client raises on blank", False)
    except CT.ThetaUnavailable:
        check("get_theta_client raises on blank", True)
    except Exception as e:  # noqa
        failures.append(f"get_theta_client wrong type: {type(e).__name__}")

    # 2. assert_theta_ready raises ThetaUnavailable + CALIBRATION_THETA_DOWN for blank AND whitespace.
    for val in ("", "   "):
        os.environ["THETA_EMAIL"] = val
        os.environ["THETA_PASSWORD"] = val
        try:
            import massive_options as MO  # reset any cached client
            MO._client = None
        except Exception:
            pass
        try:
            CT.assert_theta_ready()
            failures.append(f"assert_theta_ready did not raise for {val!r}")
        except CT.ThetaUnavailable as e:
            check(f"assert_theta_ready token for {val!r}", "CALIBRATION_THETA_DOWN" in str(e))
        except Exception as e:  # noqa
            failures.append(f"assert_theta_ready wrong type for {val!r}: {type(e).__name__}")

    # 3. _fetch_impl injection (tests) bypasses the real smoke call -> returns None, no raise.
    CT._fetch_impl = lambda *a, **k: []
    try:
        check("assert_theta_ready bypassed under _fetch_impl", CT.assert_theta_ready() is None)
    except Exception as e:  # noqa
        failures.append(f"assert_theta_ready should no-op under _fetch_impl: {e}")
    finally:
        CT._fetch_impl = None

    if failures:
        print("FAILED:", failures)
        sys.exit(1)
    print("ALL THETA HARDENING TESTS PASSED (blank/whitespace -> CALIBRATION_THETA_DOWN; _fetch_impl bypass).")


if __name__ == "__main__":
    main()
