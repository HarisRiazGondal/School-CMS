import copy
import json
from pathlib import Path

from django.test import SimpleTestCase

from scripts.release_state import validate_state


class ReleaseStateTests(SimpleTestCase):
    def setUp(self):
        self.state = json.loads((Path(__file__).resolve().parents[1] / "docs/ai-context/project_state.json").read_text())

    def test_checkpoint_is_consistent(self):
        validate_state(self.state)

    def test_skips_cannot_be_reported_as_passes(self):
        self.state["tests"]["passed"] += 1
        with self.assertRaises(ValueError):
            validate_state(self.state)

    def test_denominator_cannot_be_reduced(self):
        self.state["milestones"].pop()
        with self.assertRaises(ValueError):
            validate_state(self.state)

    def test_production_cannot_close_without_all_gate_evidence(self):
        self.state["milestones"][-1]["status"] = "Verified"
        with self.assertRaises(ValueError):
            validate_state(self.state)

    def test_acceptance_criteria_cannot_be_weakened(self):
        self.state["milestones"][-1]["criteria"] = "Code exists"
        with self.assertRaises(ValueError):
            validate_state(self.state)

    def test_readiness_label_cannot_claim_release_with_open_gates(self):
        self.state["readiness"] = "Production acceptance evidenced"
        with self.assertRaises(ValueError):
            validate_state(self.state)

    def test_verified_gate_requires_reviewable_evidence(self):
        self.state["release_gates"][0]["status"] = "verified"
        self.state["release_gates"][0].pop("evidence", None)
        with self.assertRaises(ValueError):
            validate_state(self.state)

    def test_complete_evidence_allows_closure(self):
        self.state["milestones"][-1]["status"] = "Verified"
        self.state["readiness"] = "Production acceptance evidenced"
        evidence = {"commit": "a" * 40, "checked_at": "2026-10-15T12:00:00+00:00",
                    "target": "isolated acceptance target", "artifact": "reviewed report", "reviewer": "operator"}
        for gate in self.state["release_gates"]:
            gate.update(status="verified", evidence=copy.copy(evidence))
        validate_state(self.state)
