"""Minimal sd_notify client — no python3-systemd dependency.

Used for the systemd watchdog: `Restart=always` only catches a process that EXITS, so a
deadlocked service stays "active" forever while the house goes quiet. With WatchdogSec set,
systemd kills+restarts us if the pings stop.

The ping is deliberately sent from the health monitor's sweep loop (health.py), not from a
bare timer thread: that way it proves the box is still checking mpd/the preamp, so a wedged
sweep actually trips the watchdog instead of being papered over by a thread that only sleeps.
"""
import os
import socket


def notify(state):
    """Send a status string to systemd (e.g. "WATCHDOG=1"). Returns True if it was sent.
    A no-op (False) when not running under systemd or when notifications are not allowed."""
    addr = os.environ.get("NOTIFY_SOCKET")
    if not addr:
        return False
    if addr.startswith("@"):          # abstract namespace socket
        addr = "\0" + addr[1:]
    try:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        try:
            sock.connect(addr)
            sock.sendall(state.encode("utf-8"))
            return True
        finally:
            sock.close()
    except Exception:
        return False


def watchdog_enabled():
    """True when systemd armed the watchdog for this unit (WatchdogSec= is set)."""
    return bool(os.environ.get("NOTIFY_SOCKET") and os.environ.get("WATCHDOG_USEC"))
