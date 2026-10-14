"""Test-only guard: fail every IP socket connection in this process and children."""
import os
import socket
import traceback
from pathlib import Path

_report = os.getenv('ATOPILE_TEST_NETWORK_REPORT')

def record(event):
    if _report:
        with Path(_report).open('a') as stream:
            stream.write(f'{os.getpid()} {event}\n')

record('guard-loaded')

for _method in ('connect', 'connect_ex', 'sendto'):
    _original = getattr(socket.socket, _method)
    def _guard(self, *args, _original=_original, **kwargs):
        if self.family in (socket.AF_INET, socket.AF_INET6):
            record('blocked-IP-connection ' + repr(args) + '\n' + ''.join(traceback.format_stack(limit=8)))
            raise AssertionError('Network is disabled by the offline build test')
        return _original(self, *args, **kwargs)
    setattr(socket.socket, _method, _guard)
