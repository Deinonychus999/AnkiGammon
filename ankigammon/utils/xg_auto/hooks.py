"""Frida-based event hooks for eXtreme Gammon 2.

Hooks Win32 API functions inside XG's process to detect events:
- File creation/writes (analysis complete -> output file written)
- Dialog creation (completion dialogs)

This provides event-driven completion detection, replacing or
augmenting the existing polling approach.

This module is entirely optional — XGAutomator falls back to
polling if Frida is unavailable.
"""

import json
import logging
import queue
import threading
import time
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Callable, Optional

log = logging.getLogger(__name__)

# Lazy import
_frida = None


def _ensure_frida():
    global _frida
    if _frida is None:
        import frida

        _frida = frida
    return _frida


class EventType(Enum):
    FILE_CREATED = auto()
    FILE_WRITTEN = auto()
    DIALOG_CREATED = auto()
    ANALYSIS_COMPLETE = auto()
    ERROR = auto()


@dataclass
class HookEvent:
    """An event captured by a Frida hook."""

    event_type: EventType
    data: dict = field(default_factory=dict)
    timestamp: float = 0.0


# Frida JavaScript agent — injected into the 32-bit XG process.
# Hooks Win32 API functions to detect file writes and dialog creation.
# IMPORTANT: This script is read-only (never modifies XG state).
AGENT_SCRIPT = r"""
'use strict';

// Frida 17+: Module is a constructor, not a namespace.
// Use Process.getModuleByName() to resolve exports.
const kernel32 = Process.getModuleByName('kernel32.dll');
const user32   = Process.getModuleByName('user32.dll');

// ---------------------------------------------------------------
// Hook CreateFileW — detect when XG creates files for writing
// ---------------------------------------------------------------
const CreateFileW = kernel32.getExportByName('CreateFileW');
Interceptor.attach(CreateFileW, {
    onEnter(args) {
        this.path = args[0].readUtf16String();
        this.access = args[1].toUInt32();
    },
    onLeave(retval) {
        const GENERIC_WRITE = 0x40000000;
        const INVALID_HANDLE = 0xFFFFFFFF;
        const handle = retval.toUInt32();

        if ((this.access & GENERIC_WRITE) && handle !== INVALID_HANDLE) {
            send({
                type: 'file_create',
                path: this.path,
                handle: handle,
            });
        }
    }
});

// ---------------------------------------------------------------
// Hook WriteFile — detect substantial data writes
// ---------------------------------------------------------------
const WriteFile = kernel32.getExportByName('WriteFile');
Interceptor.attach(WriteFile, {
    onEnter(args) {
        this.handle = args[0].toUInt32();
        this.bufSize = args[2].toUInt32();
    },
    onLeave(retval) {
        if (this.bufSize > 100) {
            send({
                type: 'file_write',
                handle: this.handle,
                size: this.bufSize,
            });
        }
    }
});

// ---------------------------------------------------------------
// Hook CreateWindowExW — detect dialog/window creation
// ---------------------------------------------------------------
const CreateWindowExW = user32.getExportByName('CreateWindowExW');
Interceptor.attach(CreateWindowExW, {
    onEnter(args) {
        // lpClassName (args[1]) can be a string pointer OR an ATOM
        // (small integer via MAKEINTATOM). ATOMs are <= 0xFFFF.
        const cls = args[1].toUInt32();
        this.className = cls > 0xFFFF ? args[1].readUtf16String() : null;
        this.windowName = args[2].isNull() ? null : args[2].readUtf16String();
        this.style = args[3].toUInt32();
    },
    onLeave(retval) {
        const hwnd = retval.toUInt32();
        if (hwnd && this.windowName) {
            const WS_POPUP = 0x80000000;
            const WS_DLGFRAME = 0x00400000;
            const DS_MODALFRAME = 0x00000080;
            const style = this.style >>> 0;

            if ((style & WS_POPUP) || (style & WS_DLGFRAME) || (style & DS_MODALFRAME)) {
                send({
                    type: 'dialog_create',
                    hwnd: hwnd,
                    className: this.className,
                    windowName: this.windowName,
                    style: style,
                });
            }
        }
    }
});

// ---------------------------------------------------------------
// Hook DialogBoxParamW — detect modal dialog invocations
// ---------------------------------------------------------------
try {
    const DialogBoxParamW = user32.getExportByName('DialogBoxParamW');
    Interceptor.attach(DialogBoxParamW, {
        onEnter(args) {
            send({
                type: 'modal_dialog',
                source: 'DialogBoxParamW',
                templateName: args[1].toUInt32(),
                hwndParent: args[2].toUInt32(),
            });
        }
    });
} catch (e) {
    // DialogBoxParamW may not be resolvable on all systems
}

// ---------------------------------------------------------------
// Hook CloseHandle — track file handle lifecycle
// ---------------------------------------------------------------
const CloseHandle = kernel32.getExportByName('CloseHandle');
Interceptor.attach(CloseHandle, {
    onEnter(args) {
        this.handle = args[0].toUInt32();
    },
    onLeave(retval) {
        if (retval.toUInt32()) {
            send({
                type: 'handle_close',
                handle: this.handle,
            });
        }
    }
});
"""




class XGEventHooks:
    """Frida-based event hook system for eXtreme Gammon 2.

    Attaches Frida to XG's process and intercepts Win32 API calls
    to provide event-driven completion detection.

    Usage:
        hooks = XGEventHooks()
        hooks.attach(pid=1234)

        # Blocking wait
        event = hooks.wait_for_event(EventType.ANALYSIS_COMPLETE, timeout=600)

        # Or register callbacks
        hooks.on_analysis_complete(my_callback)

        hooks.detach()
    """

    def __init__(self, headless: bool = False):
        self._session = None
        self._script = None
        self._attached = False
        self._event_queue: queue.Queue[HookEvent] = queue.Queue()
        self._callbacks: dict[EventType, list[Callable]] = {
            et: [] for et in EventType
        }
        # Track open file handles -> paths for write correlation
        self._file_handles: dict[int, str] = {}
        self._lock = threading.Lock()
        self._completion_patterns: list[str] = [
            "complete",
            "finish",
            "done",
            "result",
        ]

    @property
    def is_attached(self) -> bool:
        return self._attached

    def attach(self, pid: int) -> bool:
        """Attach Frida to the XG process.

        Frida handles 64-bit Python -> 32-bit target injection
        automatically via its frida-agent architecture.

        Returns True if attachment succeeded.
        """
        frida = _ensure_frida()

        try:
            self._session = frida.attach(pid)
            self._script = self._session.create_script(AGENT_SCRIPT)
            self._script.on("message", self._on_message)
            self._script.load()
            self._attached = True
            log.info(
                "Frida attached to PID %d", pid
            )
            return True
        except Exception as e:
            log.error("Failed to attach Frida: %s", e)
            self._cleanup()
            return False

    def detach(self) -> None:
        """Detach Frida from the XG process."""
        self._cleanup()
        log.info("Frida hooks detached.")

    def _cleanup(self):
        """Release Frida resources."""
        try:
            if self._script:
                self._script.unload()
        except Exception:
            pass
        try:
            if self._session:
                self._session.detach()
        except Exception:
            pass
        self._script = None
        self._session = None
        self._attached = False
        self._file_handles.clear()

    def _on_message(self, message: dict, data: Optional[bytes]) -> None:
        """Handle messages from the Frida agent script.

        Runs on Frida's message thread. Translates raw messages into
        typed HookEvents and dispatches them.
        """
        if message.get("type") != "send":
            if message.get("type") == "error":
                desc = message.get("description", "")
                stack = message.get("stack", "")
                line = message.get("lineNumber", "?")
                log.error("Frida script error (line %s): %s", line, desc)
                if stack:
                    log.debug("Frida stack:\n%s", stack)
                self._emit_event(
                    HookEvent(
                        event_type=EventType.ERROR,
                        data={"error": desc},
                        timestamp=time.time(),
                    )
                )
            return

        payload = message.get("payload", {})
        msg_type = payload.get("type", "")
        now = time.time()

        if msg_type == "file_create":
            path = payload.get("path", "")
            handle = payload.get("handle", 0)
            log.debug("Hook: CreateFileW(%s) -> handle=%d", path, handle)

            # Track handle -> path mapping
            if handle:
                with self._lock:
                    self._file_handles[handle] = path

            self._emit_event(
                HookEvent(
                    event_type=EventType.FILE_CREATED,
                    data={"path": path, "handle": handle},
                    timestamp=now,
                )
            )

        elif msg_type == "file_write":
            handle = payload.get("handle", 0)
            size = payload.get("size", 0)

            with self._lock:
                path = self._file_handles.get(handle, "")

            log.debug("Hook: WriteFile(handle=%d, size=%d, path=%s)", handle, size, path)
            self._emit_event(
                HookEvent(
                    event_type=EventType.FILE_WRITTEN,
                    data={"handle": handle, "size": size, "path": path},
                    timestamp=now,
                )
            )

        elif msg_type in ("dialog_create", "modal_dialog"):
            window_name = payload.get("windowName", "") or ""
            class_name = payload.get("className", "") or ""
            log.debug("Hook: dialog created: '%s' [%s]", window_name, class_name)

            event = HookEvent(
                event_type=EventType.DIALOG_CREATED,
                data={
                    "hwnd": payload.get("hwnd", 0),
                    "window_name": window_name,
                    "class_name": class_name,
                    "source": payload.get("source", "CreateWindowExW"),
                },
                timestamp=now,
            )
            self._emit_event(event)

            # Check if this is a completion dialog
            name_lower = window_name.lower()
            if any(pat in name_lower for pat in self._completion_patterns):
                log.info(
                    "Completion dialog detected: '%s'", window_name
                )
                self._emit_event(
                    HookEvent(
                        event_type=EventType.ANALYSIS_COMPLETE,
                        data={
                            "trigger": "dialog",
                            "window_name": window_name,
                        },
                        timestamp=now,
                    )
                )

        elif msg_type == "debug":
            log.debug("Frida: %s", payload.get("msg", ""))

        elif msg_type == "handle_close":
            handle = payload.get("handle", 0)
            with self._lock:
                path = self._file_handles.pop(handle, "")
            if path:
                log.debug("Hook: CloseHandle(%d) -> file complete: %s", handle, path)

    def _emit_event(self, event: HookEvent) -> None:
        """Put event on queue and invoke registered callbacks."""
        self._event_queue.put(event)

        with self._lock:
            callbacks = list(self._callbacks.get(event.event_type, []))

        for callback in callbacks:
            try:
                callback(event)
            except Exception as e:
                log.error("Event callback error: %s", e)

    # ------------------------------------------------------------------
    # Public API: register callbacks
    # ------------------------------------------------------------------

    def on_analysis_complete(
        self, callback: Callable[[HookEvent], None]
    ) -> None:
        """Register a callback for analysis completion events."""
        with self._lock:
            self._callbacks[EventType.ANALYSIS_COMPLETE].append(callback)

    def on_dialog_created(
        self, callback: Callable[[HookEvent], None]
    ) -> None:
        """Register a callback for dialog creation events."""
        with self._lock:
            self._callbacks[EventType.DIALOG_CREATED].append(callback)

    def on_file_written(
        self, callback: Callable[[HookEvent], None]
    ) -> None:
        """Register a callback for file write events."""
        with self._lock:
            self._callbacks[EventType.FILE_WRITTEN].append(callback)

    # ------------------------------------------------------------------
    # Public API: blocking wait
    # ------------------------------------------------------------------

    def wait_for_event(
        self,
        event_type: EventType,
        timeout: float = 600.0,
    ) -> Optional[HookEvent]:
        """Block until an event of the given type arrives, or timeout.

        Returns the event, or None if timed out.
        """
        deadline = time.time() + timeout

        while time.time() < deadline:
            remaining = deadline - time.time()
            if remaining <= 0:
                break
            try:
                event = self._event_queue.get(timeout=min(1.0, remaining))
                if event.event_type == event_type:
                    return event
                # Non-matching events are consumed (callbacks already fired)
            except queue.Empty:
                continue

        return None

    def drain_events(self) -> list[HookEvent]:
        """Drain all pending events from the queue."""
        events = []
        while True:
            try:
                events.append(self._event_queue.get_nowait())
            except queue.Empty:
                break
        return events
