"""Scenario-aware routing for EDQ tests.

Keeps per-scenario manual-vs-automatic routing in one place so the API,
batch scan flow, and test engine apply the same rules.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.models.test_result import TestTier


DIRECT_SCENARIOS = {"direct", "direct_cable"}

_SCENARIO_MANUAL_ROUTING: dict[str, dict[str, str]] = {
    "test_lab": {
        "U03": "Switch negotiation must be verified manually in the test lab scenario.",
        "U04": "DHCP behaviour must be verified manually in the test lab scenario.",
        "U26": "NTP synchronisation requires lab-side observation in the test lab scenario.",
        "U29": "DNS support requires lab-side observation in the test lab scenario.",
    },
    "site_network": {
        "U03": "Switch negotiation must be verified manually on a live site network.",
        "U04": "DHCP behaviour must be verified manually on a live site network.",
        "U26": "NTP synchronisation requires manual evidence on a live site network.",
        "U29": "DNS support requires manual evidence on a live site network.",
    },
}


@dataclass(frozen=True)
class ScenarioRoutingDecision:
    tier: str
    manual_reason: str | None = None


def normalize_connection_scenario(connection_scenario: str | None) -> str:
    scenario = (connection_scenario or "direct").strip().lower()
    if scenario in DIRECT_SCENARIOS:
        return "direct"
    return scenario or "direct"


def get_scenario_routing_decision(test_id: str, base_tier: str, connection_scenario: str | None) -> ScenarioRoutingDecision:
    scenario = normalize_connection_scenario(connection_scenario)
    if base_tier != TestTier.AUTOMATIC.value:
        return ScenarioRoutingDecision(tier=base_tier)

    manual_routes = _SCENARIO_MANUAL_ROUTING.get(scenario, {})
    manual_reason = manual_routes.get(test_id)
    if manual_reason:
        return ScenarioRoutingDecision(
            tier=TestTier.GUIDED_MANUAL.value,
            manual_reason=manual_reason,
        )

    return ScenarioRoutingDecision(tier=base_tier)


def get_manual_routing_note(test_id: str, connection_scenario: str | None) -> str | None:
    scenario = normalize_connection_scenario(connection_scenario)
    return _SCENARIO_MANUAL_ROUTING.get(scenario, {}).get(test_id)


def is_manual_routing_note(value: str | None) -> bool:
    if not value:
        return False
    return any(
        value == note
        for scenario_notes in _SCENARIO_MANUAL_ROUTING.values()
        for note in scenario_notes.values()
    )
