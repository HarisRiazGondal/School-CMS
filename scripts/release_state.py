"""Validate dashboard accounting and prevent accidental closure of release gates.

Recorded evidence still requires independent operator review; this validator does
not authenticate reports or certify a deployment.
"""
from datetime import datetime
import re

MILESTONES = (
    "Foundation and academics", "Session auth and scoped portals",
    "Student identity and year progression", "Basic attendance and classwork",
    "Assessment and report cards", "Fees and accounting",
    "Oversight and complete operations", "Production pilot release",
)
RELEASE_GATES = frozenset({
    "postgresql", "deployment", "authentication", "uploads", "smtp",
    "recovery", "accessibility", "privacy_security", "hosted_pilot",
})
PRODUCTION_CRITERIA = "PostgreSQL, privacy/security, uploads, SMTP, backup restoration, accessibility and hosted pilot acceptance are evidenced."


def validate_state(state):
    """Raise ValueError on misleading totals, changed scoring, or absent evidence."""
    tests = state["tests"]
    counts = [tests.get(key, 0) for key in ("passed", "skipped", "failed", "total")]
    if any(type(value) is not int or value < 0 for value in counts):
        raise ValueError("Test counts must be nonnegative integers")
    if sum(counts[:3]) != counts[3]:
        raise ValueError("Test total must equal passed + skipped + failed")
    milestones = state["milestones"]
    if tuple(item["name"] for item in milestones) != MILESTONES:
        raise ValueError("The eight named milestone scoring denominator must be preserved")
    if milestones[-1]["criteria"] != PRODUCTION_CRITERIA:
        raise ValueError("Production acceptance criteria must be preserved")
    if any(item["status"] not in {"Verified", "In progress", "Not started"} for item in milestones):
        raise ValueError("Unknown milestone status")
    gates = state["release_gates"]
    if len(gates) != len(RELEASE_GATES) or {gate["id"] for gate in gates} != RELEASE_GATES:
        raise ValueError("Every named release gate must appear exactly once")
    for gate in gates:
        if gate["status"] not in {"verified", "in_progress", "blocked"}:
            raise ValueError("Unknown release gate status")
        if gate["status"] == "verified":
            evidence = gate.get("evidence", {})
            if not all(isinstance(evidence.get(key), str) and evidence[key].strip()
                       for key in ("commit", "checked_at", "target", "artifact", "reviewer")):
                raise ValueError("Verified gates require commit, time, target, artifact and reviewer")
            if not re.fullmatch(r"[a-f0-9]{40}", evidence["commit"]):
                raise ValueError("Evidence requires a full Git commit SHA")
            try:
                timestamp = datetime.fromisoformat(evidence["checked_at"].replace("Z", "+00:00"))
            except ValueError as exc:
                raise ValueError("Invalid evidence timestamp") from exc
            if timestamp.tzinfo is None:
                raise ValueError("Evidence timestamp must include a timezone")
    if milestones[-1]["status"] == "Verified" and any(gate["status"] != "verified" for gate in gates):
        raise ValueError("Production milestone requires every release gate to be verified")
    expected_readiness = ("Production acceptance evidenced" if milestones[-1]["status"] == "Verified"
                          else "Release candidate; production acceptance pending")
    if state["readiness"] != expected_readiness:
        raise ValueError("Readiness label must agree with the production milestone")

