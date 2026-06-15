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
_post_reset_hooks = []


def register_post_reset_hook(fn):
    """Register cleanup (e.g. remove flag files) after chaos reset or auto-expire."""
    _post_reset_hooks.append(fn)


def _run_post_reset_hooks():
    for hook in _post_reset_hooks:
        try:
            hook()
        except Exception:
            pass


def _expire_if_needed_unlocked() -> bool:
    if _chaos["expires_at"] and time.time() > _chaos["expires_at"]:
        reset_unlocked()
        return True
    return False


def _expire_if_needed():
    expired = False
    with _lock:
        expired = _expire_if_needed_unlocked()
    if expired:
        _run_post_reset_hooks()


def get_status():
    with _lock:
        expired = _expire_if_needed_unlocked()
        status = {
            "active": bool(_chaos["active_action"]),
            "action": _chaos["active_action"],
            "latency_ms": _chaos["latency_ms"],
            "drop_rate": _chaos["drop_rate"],
            "killed": _chaos["killed"],
            "cpu_spike": _chaos["cpu_spike"],
            "thermal_spike": _chaos["thermal_spike"],
            "expires_at": _chaos["expires_at"] or None,
        }
    if expired:
        _run_post_reset_hooks()
    return status


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
    _run_post_reset_hooks()
    return get_status()


def should_drop_health():
    with _lock:
        expired = _expire_if_needed_unlocked()
        if _chaos["killed"]:
            result = True
        elif _chaos["drop_rate"] > 0:
            result = random.randint(1, 100) <= _chaos["drop_rate"]
        else:
            result = False
    if expired:
        _run_post_reset_hooks()
    return result


def health_delay_seconds():
    with _lock:
        expired = _expire_if_needed_unlocked()
        delay = _chaos["latency_ms"] / 1000.0
    if expired:
        _run_post_reset_hooks()
    return delay


def cpu_spike_active():
    with _lock:
        expired = _expire_if_needed_unlocked()
        active = _chaos["cpu_spike"]
    if expired:
        _run_post_reset_hooks()
    return active


def thermal_spike_active():
    with _lock:
        expired = _expire_if_needed_unlocked()
        active = _chaos["thermal_spike"]
    if expired:
        _run_post_reset_hooks()
    return active
