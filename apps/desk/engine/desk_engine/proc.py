"""Process helpers that also work on Windows (the desk engine may run without the vstudio library: mock mode).

``pid_alive`` never signals (``os.kill(pid, 0)`` TERMINATES the process on Windows); ``kill_tree`` ends a child
and what it started: POSIX - a signal to its process group (children are started with ``start_new_session=True``);
Windows - ``taskkill /T /F`` (console children have no graceful signal), else TerminateProcess. The engine library has
the same helpers in ``vstudio.oscompat``.
"""
import os
import signal
import subprocess

WINDOWS = os.name == "nt"
CREATE_NO_WINDOW = 0x08000000


def pid_alive(pid):
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        return False
    if pid <= 0:
        return False
    if WINDOWS:
        import ctypes
        k = ctypes.WinDLL("kernel32", use_last_error=True)
        h = k.OpenProcess(0x1000, False, pid)            # PROCESS_QUERY_LIMITED_INFORMATION
        if not h:
            return ctypes.get_last_error() == 5          # access denied: exists, another user's
        try:
            code = ctypes.c_ulong()
            return bool(k.GetExitCodeProcess(h, ctypes.byref(code))) and code.value == 259   # STILL_ACTIVE
        finally:
            k.CloseHandle(h)
    try:
        os.kill(pid, 0)
        return True
    except PermissionError:
        return True
    except OSError:
        return False


def kill_tree(p, sig=signal.SIGTERM):
    """End Popen ``p`` and its children. -> False when it had already exited."""
    if p.poll() is not None:
        return False
    if WINDOWS:
        try:
            r = subprocess.run(["taskkill", "/PID", str(p.pid), "/T", "/F"], capture_output=True,
                               creationflags=CREATE_NO_WINDOW, timeout=15)
            if r.returncode == 0:
                return True
        except (OSError, subprocess.SubprocessError):
            pass
        try:
            p.kill()
        except OSError:
            pass
        return True
    try:
        os.killpg(p.pid, sig)
    except OSError:
        try:
            p.send_signal(sig)
        except OSError:
            pass
    return True


def interrupt_pid(pid):
    """Stop the run with process id ``pid`` (started with ``start_new_session=True``) and what it started: POSIX -
    SIGINT to its process group (the engine stops at a safe point), else to the process; Windows - ``taskkill /T /F``
    (no graceful signal reaches a console child), else TerminateProcess. -> False when ``pid`` is not a number."""
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        return False
    if WINDOWS:
        try:
            r = subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True,
                               creationflags=CREATE_NO_WINDOW, timeout=15)
            if r.returncode == 0:
                return True
        except (OSError, subprocess.SubprocessError):
            pass
        try:
            os.kill(pid, signal.SIGTERM)                  # TerminateProcess on Windows
        except OSError:
            pass
        return True
    try:
        os.killpg(pid, signal.SIGINT)
    except OSError:
        try:
            os.kill(pid, signal.SIGINT)
        except OSError:
            pass
    return True
