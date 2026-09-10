"""Serialize Windows audio lifetime on one COM-initialized owner thread."""

from contextlib import contextmanager
import ctypes
import queue
import threading


@contextmanager
def _com_scope():
    ole = ctypes.WinDLL("ole32")
    ole.CoInitializeEx.argtypes = (ctypes.c_void_p, ctypes.c_uint32)
    ole.CoInitializeEx.restype = ctypes.c_long
    ole.CoUninitialize.argtypes = ()
    ole.CoUninitialize.restype = None
    result = ole.CoInitializeEx(None, 0) & 0xFFFFFFFF  # COINIT_MULTITHREADED
    if result not in (0, 1, 0x80010106):  # S_OK, S_FALSE, RPC_E_CHANGED_MODE
        raise OSError(f"Audio thread COM initialization failed (0x{result:08X})")
    try:
        yield
    finally:
        if result in (0, 1):
            ole.CoUninitialize()


class AudioOwner:
    def __init__(self):
        self._queue = queue.Queue()
        self._lock = threading.Lock()
        self._ready = threading.Event()
        self._closing = False
        self._failure = None
        self._thread = threading.Thread(target=self._run, name="Utterleaf audio", daemon=True)
        self._thread.start()
        self._ready.wait()
        if self._failure is not None:
            self._thread.join()
            raise self._failure

    def _run(self):
        try:
            with _com_scope():
                self._ready.set()
                while True:
                    fn, event, result, final = self._queue.get()
                    try:
                        result.append((True, fn()))
                    except BaseException as exc:
                        result.append((False, exc))
                    finally:
                        event.set()
                    if final:
                        if not result[0][0]:
                            self._failure = result[0][1]
                        break
        except BaseException as exc:
            self._failure = exc
        finally:
            self._ready.set()

    def call(self, fn):
        if threading.current_thread() is self._thread:
            return fn()
        event, result = threading.Event(), []
        with self._lock:
            if self._closing:
                raise RuntimeError("Audio owner is closed")
            self._queue.put((fn, event, result, False))
        event.wait()
        success, value = result[0]
        if not success:
            raise value
        return value

    def close(self, teardown):
        """Drain accepted calls, tear down on owner, release COM, and join."""
        if threading.current_thread() is self._thread:
            raise RuntimeError("Audio owner shutdown must be requested outside its worker")
        with self._lock:
            if not self._closing:
                self._closing = True
                self._queue.put((teardown, threading.Event(), [], True))
        self._thread.join()
        if self._failure is not None:
            raise self._failure
