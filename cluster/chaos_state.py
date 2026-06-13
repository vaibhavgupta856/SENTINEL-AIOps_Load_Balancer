import random
import time
import threading

_chaos = {
    "latency_ms": 0,
    "drop_rate": 0,
    "killed": False,
    "cpu_spike": False,
    "thermal_spike": False,
    "expires_at": 0,
    "active_action": None,
}
_lock = threading.Lock()


def _expire_if_needed():
    if _chaos["expires_at"] and time.time() > _chaos["expires_at"]:
        reset()


def get_status():
    with _lock:
        _expire_if_needed()
        return {
            "active": bool(_chaos["active_action"]),
            "action": _chaos["active_action"],
            "latency_ms": _chaos["latency_ms"],
            "drop_rate": _chaos["drop_rate"],
            "killed": _chaos["killed"],
            "cpu_spike": _chaos["cpu_spike"],
            "thermal_spike": _chaos["thermal_spike"],
            "expires_at": _chaos["expires_at"] or None,
        }


def apply(action, duration=30, latency_ms=3000, drop_rate=80):
    with _lock:
        reset_unlocked()
        _chaos["active_action"] = action
        _chaos["expires_at"] = time.time() + duration if duration > 0 else 0

        if action == "latency_spike":
            _chaos["latency_ms"] = latency_ms
        elif action == "packet_drop":
            _chaos["drop_rate"] = drop_rate
        elif action == "cpu_spike":
            _chaos["cpu_spike"] = True
        elif action == "thermal_spike":
            _chaos["thermal_spike"] = True
        elif action == "node_kill":
            _chaos["killed"] = True

    return get_status()


def reset_unlocked():
    _chaos["latency_ms"] = 0
    _chaos["drop_rate"] = 0
    _chaos["killed"] = False
    _chaos["cpu_spike"] = False
    _chaos["thermal_spike"] = False
    _chaos["expires_at"] = 0
    _chaos["active_action"] = None


def reset():
    with _lock:
        reset_unlocked()
    return get_status()


def should_drop_health():
    with _lock:
        _expire_if_needed()
        if _chaos["killed"]:
            return True
        if _chaos["drop_rate"] > 0:
            return random.randint(1, 100) <= _chaos["drop_rate"]
        return False


def health_delay_seconds():
    with _lock:
        _expire_if_needed()
        return _chaos["latency_ms"] / 1000.0


def cpu_spike_active():
    with _lock:
        _expire_if_needed()
        return _chaos["cpu_spike"]


def thermal_spike_active():
    with _lock:
        _expire_if_needed()
        return _chaos["thermal_spike"]
