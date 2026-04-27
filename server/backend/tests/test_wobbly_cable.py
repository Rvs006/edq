from app.services.wobbly_cable import _service_probe_satisfied, _tcp_stack_responded
from app.services.wobbly_cable import WobblyCableHandler


def test_tcp_refused_counts_as_tcp_stack_reachable():
    assert _tcp_stack_responded("tcp_refused:135") is True


def test_tcp_refused_only_satisfies_service_probe_without_known_service_baseline():
    assert _service_probe_satisfied("tcp_refused:135", []) is True
    assert _service_probe_satisfied("tcp_refused:135", [80]) is False


def test_new_cable_handler_starts_outside_tcp_grace_window():
    class DummyManager:
        async def broadcast(self, *_args, **_kwargs):
            return None

    handler = WobblyCableHandler("192.168.4.64", "run-grace-test", DummyManager())
    try:
        assert handler._tcp_grace_until == 0.0
    finally:
        handler.stop()
