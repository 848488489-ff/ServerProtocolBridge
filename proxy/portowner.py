"""Find the process that is listening on a TCP port.

A failed ``bind()`` is fatal by design: the program never moves to another port
and never continues with fewer listeners, because that would silently change
the endpoint that clients and automation depend on.  This module only improves
the error message -- it answers "who owns the port?" so the failure names the
conflicting program instead of leaving the operator with a bare WinError 10013.

Windows reads the listener table through ``GetExtendedTcpTable`` (iphlpapi),
which the standard library reaches through ``ctypes``: no extra dependency and
no native helper binary.  Other platforms fall back to ``lsof`` when it is
installed; without it the caller keeps the original operating-system error.

The lookup is advisory.  It is a snapshot taken after the bind failed, so a
port can still change between the two calls; :func:`listener` returns ``None``
when it cannot prove an owner, and callers must never guess one.
"""

from __future__ import annotations

import ctypes
import os
import socket
import subprocess

# Windows constants (ctypes does not expose the table classes).
_AF_INET = 2
_AF_INET6 = 23
_TCP_TABLE_OWNER_PID_LISTENER = 3
_PROCESS_QUERY_LIMITED_INFORMATION = 0x1000


class _TcpRowOwnerPid(ctypes.Structure):
    _fields_ = [
        ('dwState', ctypes.c_uint32),
        ('dwLocalAddr', ctypes.c_uint32),
        ('dwLocalPort', ctypes.c_uint32),
        ('dwRemoteAddr', ctypes.c_uint32),
        ('dwRemotePort', ctypes.c_uint32),
        ('dwOwningPid', ctypes.c_uint32),
    ]


class _Tcp6RowOwnerPid(ctypes.Structure):
    _fields_ = [
        ('ucLocalAddr', ctypes.c_ubyte * 16),
        ('dwLocalScopeId', ctypes.c_uint32),
        ('dwLocalPort', ctypes.c_uint32),
        ('ucRemoteAddr', ctypes.c_ubyte * 16),
        ('dwRemoteScopeId', ctypes.c_uint32),
        ('dwRemotePort', ctypes.c_uint32),
        ('dwState', ctypes.c_uint32),
        ('dwOwningPid', ctypes.c_uint32),
    ]


def _windows_table(family: int, row_type, port: int) -> int:
    """Owning PID of the IPv4/IPv6 listener on *port*, or 0 when not found."""
    import ctypes.wintypes as wintypes

    iphlpapi = ctypes.WinDLL('iphlpapi.dll')
    get_table = iphlpapi.GetExtendedTcpTable
    get_table.argtypes = [ctypes.c_void_p, ctypes.POINTER(wintypes.DWORD),
                          wintypes.BOOL, wintypes.ULONG, ctypes.c_int,
                          wintypes.ULONG]
    get_table.restype = wintypes.DWORD

    size = wintypes.DWORD(0)
    get_table(None, ctypes.byref(size), False, family,
              _TCP_TABLE_OWNER_PID_LISTENER, 0)
    if size.value < ctypes.sizeof(wintypes.DWORD):
        return 0
    buffer = ctypes.create_string_buffer(size.value)
    status = get_table(buffer, ctypes.byref(size), False, family,
                       _TCP_TABLE_OWNER_PID_LISTENER, 0)
    if status != 0:
        return 0

    count = ctypes.cast(buffer, ctypes.POINTER(wintypes.DWORD)).contents.value
    offset = ctypes.sizeof(wintypes.DWORD)
    stride = ctypes.sizeof(row_type)
    for index in range(count):
        start = offset + index * stride
        row = row_type.from_buffer_copy(buffer.raw[start:start + stride])
        if socket.ntohs(row.dwLocalPort & 0xFFFF) == int(port):
            return int(row.dwOwningPid)
    return 0


def _process_name(pid: int) -> str:
    """Executable name for *pid*, or '' when it cannot be read."""
    if pid <= 0:
        return ''
    import ctypes.wintypes as wintypes

    kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL,
                                     wintypes.DWORD]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.QueryFullProcessImageNameW.argtypes = [
        wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR,
        ctypes.POINTER(wintypes.DWORD)]
    kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL

    handle = kernel32.OpenProcess(_PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return ''
    try:
        size = wintypes.DWORD(1024)
        buffer = ctypes.create_unicode_buffer(size.value)
        if not kernel32.QueryFullProcessImageNameW(
                handle, 0, buffer, ctypes.byref(size)):
            return ''
        return os.path.basename(buffer.value)
    finally:
        kernel32.CloseHandle(handle)


def _windows_listener(port: int) -> dict | None:
    for family, row_type in ((_AF_INET, _TcpRowOwnerPid),
                             (_AF_INET6, _Tcp6RowOwnerPid)):
        pid = _windows_table(family, row_type, port)
        if pid:
            return {'pid': pid, 'process': _process_name(pid) or '?'}
    return None


def _posix_listener(port: int) -> dict | None:
    import shutil

    lsof = shutil.which('lsof')
    if not lsof:
        return None
    try:
        completed = subprocess.run(
            [lsof, '-nP', '-iTCP:%d' % int(port), '-sTCP:LISTEN', '-Fpc'],
            capture_output=True, text=True, timeout=3)
    except (OSError, subprocess.SubprocessError):
        return None
    pid, process = 0, ''
    for line in (completed.stdout or '').splitlines():
        if line.startswith('p'):
            pid = int(line[1:] or 0)
        elif line.startswith('c'):
            process = line[1:]
    return {'pid': pid, 'process': process or '?'} if pid else None


def listener(port: int) -> dict | None:
    """Return ``{'pid': int, 'process': str}`` for the TCP listener on *port*.

    ``None`` means "not proven", not "free": the caller must keep the original
    bind error in that case.
    """
    try:
        if os.name == 'nt':
            return _windows_listener(port)
        return _posix_listener(port)
    except Exception:
        # Diagnostics must never replace the real bind error with their own.
        return None
