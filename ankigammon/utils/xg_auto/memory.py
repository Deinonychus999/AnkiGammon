"""Runtime memory reader for eXtreme Gammon 2.

Reads application state directly from XG's process memory using pymem.
Addresses are loaded from an external JSON file (xg_addresses.json)
discovered during setup using the memory discovery pipeline.

Key insight: XG is a Delphi XE app (not Delphi 7). The VMT layout uses
vmtSelfPtr=-88, vmtClassName=-56. Strings are UnicodeString (UTF-16).
The form Self pointer is obtained via the Delphi ControlAtom window
property, not GWL_USERDATA (which returns 0 for this app).

This module is entirely optional — XGAutomator falls back to its
existing polling strategy if memory reading is unavailable.
"""

import ctypes
import ctypes.wintypes as wt
import json
import logging
import struct
from pathlib import Path
from typing import Any, Optional

log = logging.getLogger(__name__)

# Lazy import — pymem may not be installed
_pymem = None


def _ensure_pymem():
    global _pymem
    if _pymem is None:
        import pymem

        _pymem = pymem
    return _pymem


user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

# Delphi XE VMT offsets (NOT Delphi 7!)
VMT_SELF_PTR = -88
VMT_CLASS_NAME = -56
VMT_INSTANCE_SIZE = -52
VMT_PARENT = -48


class AddressMap:
    """Memory address configuration loaded from xg_addresses.json.

    The JSON file maps symbolic names (like "analysis_running") to
    pointer chains and types, enabling the reader to find values
    in XG's process memory.
    """

    def __init__(self, data: dict):
        self.image_base = int(data.get("image_base", "0x400000"), 16)
        self.aslr = data.get("aslr", False)
        self.form_class = data.get("form_class", "TMainX")
        self.offsets: dict = data.get("offsets", {})
        self.vmt_addresses: dict = data.get("vmt_addresses", {})
        self.tmainx_field_offsets: dict = data.get("tmainx_field_offsets", {})
        self.tcomponent_offsets: dict = data.get("tcomponent_offsets", {})
        self.ttimer_offsets: dict = data.get("ttimer_offsets", {})
        self.twincontrol_offsets: dict = data.get("twincontrol_offsets", {})

    @classmethod
    def load(cls, path: Path) -> "AddressMap":
        with open(path, encoding="utf-8") as f:
            return cls(json.load(f))

    def get_chain(self, key: str) -> Optional[list]:
        entry = self.offsets.get(key)
        if entry is None:
            return None
        return entry["chain"]

    def get_type(self, key: str) -> Optional[str]:
        entry = self.offsets.get(key)
        return entry.get("type") if entry else None


class XGMemoryReader:
    """Read application state from eXtreme Gammon 2's process memory.

    All public read methods return None on failure rather than raising,
    to support graceful fallback in the automator.

    Usage:
        reader = XGMemoryReader(address_map_path="xg_addresses.json")
        reader.attach(hwnd=0x12345)

        if reader.is_analysis_running() is False:
            print("Analysis done!")

        reader.detach()
    """

    def __init__(self, address_map_path: Optional[Path | str] = None):
        self._pm = None
        self._attached = False
        self._form_ptr: int = 0
        self._hwnd: int = 0
        self._address_map: Optional[AddressMap] = None

        if address_map_path:
            path = Path(address_map_path)
            if path.exists():
                try:
                    self._address_map = AddressMap.load(path)
                    log.info("Loaded address map from %s", path)
                except Exception as e:
                    log.warning("Failed to load address map: %s", e)

    @property
    def is_attached(self) -> bool:
        return self._attached and self._pm is not None

    def attach(self, hwnd: int) -> bool:
        """Attach to XG's process via its window handle.

        Discovers the form Self pointer using Delphi's ControlAtom
        window property mechanism. Returns True if successful.
        """
        pymem_mod = _ensure_pymem()
        self._hwnd = hwnd

        try:
            # Get PID and ThreadID from HWND
            pid = wt.DWORD()
            tid = user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if pid.value == 0:
                log.error("Could not get PID for hwnd 0x%X", hwnd)
                return False

            self._pm = pymem_mod.Pymem()
            self._pm.open_process_from_id(pid.value)

            # Get form pointer via Delphi ControlAtom
            self._form_ptr = self._get_form_pointer_via_control_atom(
                hwnd, tid
            )
            if self._form_ptr == 0:
                log.warning(
                    "Could not get form pointer via ControlAtom. "
                    "Memory reading will be limited."
                )
            else:
                # Validate by reading class name
                class_name = self._read_class_name(self._form_ptr)
                if class_name:
                    log.info(
                        "Form object at 0x%08X, class=%s",
                        self._form_ptr,
                        class_name,
                    )
                    expected = (
                        self._address_map.form_class
                        if self._address_map
                        else "TMainX"
                    )
                    if class_name != expected:
                        log.warning(
                            "Expected class %s, got %s", expected, class_name
                        )
                else:
                    log.warning("Could not read class name at form pointer")

            self._attached = True
            log.info("Attached to XG process (PID=%d)", pid.value)
            return True

        except Exception as e:
            log.error("Failed to attach to XG process: %s", e)
            self._pm = None
            return False

    def detach(self) -> None:
        """Detach from the XG process."""
        if self._pm:
            try:
                self._pm.close_process()
            except Exception:
                pass
        self._pm = None
        self._attached = False
        self._form_ptr = 0
        log.info("Memory reader detached.")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_form_pointer_via_control_atom(
        self, hwnd: int, thread_id: int
    ) -> int:
        """Get the Delphi form Self pointer via ControlAtom window property.

        In Delphi XE, VCL stores the control object pointer as a window
        property named 'ControlOfs{HInstance:08X}{ThreadId:08X}'.
        HInstance for XG is 0x00400000 (image base, since ASLR is off).
        """
        hinstance = (
            self._address_map.image_base if self._address_map else 0x00400000
        )
        atom_name = f"ControlOfs{hinstance:08X}{thread_id:08X}"

        try:
            # Find the global atom
            GlobalFindAtomW = kernel32.GlobalFindAtomW
            GlobalFindAtomW.restype = wt.ATOM
            GlobalFindAtomW.argtypes = [wt.LPCWSTR]
            atom = GlobalFindAtomW(atom_name)
            if not atom:
                log.debug("GlobalFindAtom('%s') returned 0", atom_name)
                return 0

            # Get the property value using the atom
            GetPropW = user32.GetPropW
            GetPropW.restype = wt.HANDLE
            GetPropW.argtypes = [wt.HWND, wt.LPCWSTR]
            ptr = GetPropW(hwnd, ctypes.cast(atom, wt.LPCWSTR))
            if ptr:
                return ptr & 0xFFFFFFFF
        except Exception as e:
            log.debug("ControlAtom lookup failed: %s", e)

        return 0

    def _read_ptr(self, addr: int) -> int:
        """Read a 32-bit pointer from process memory."""
        try:
            data = self._pm.read_bytes(addr, 4)
            return struct.unpack("<I", data)[0]
        except Exception:
            return 0

    def _follow_chain(self, key: str) -> Optional[int]:
        """Follow a pointer chain from the address map to reach a field.

        The chain format is a list like ["tmainx_self", "+0x1268", "+0x48"].
        - "tmainx_self" is replaced with the discovered form pointer
        - "+0xNNN" entries: dereference current as pointer, then add offset
          (except the last entry, which is just added without dereference)
        """
        if not self._address_map:
            return None

        chain = self._address_map.get_chain(key)
        if chain is None:
            return None

        current = 0
        for i, step in enumerate(chain):
            if step == "tmainx_self":
                current = self._form_ptr
                if current == 0:
                    return None
            elif isinstance(step, str) and step.startswith("+"):
                offset = int(step, 16)
                if i < len(chain) - 1:
                    # Intermediate: read pointer at current + offset
                    current = self._read_ptr(current + offset)
                    if current == 0:
                        return None
                else:
                    # Last: just add offset to get target address
                    current = current + offset
            elif isinstance(step, int):
                if i < len(chain) - 1:
                    current = self._read_ptr(current + step)
                    if current == 0:
                        return None
                else:
                    current = current + step
            else:
                return None

        return current

    def _read_class_name(self, obj_ptr: int) -> Optional[str]:
        """Read the Delphi class name of an object via its VMT.

        Uses Delphi XE VMT layout (vmtClassName at offset -56).
        """
        try:
            vmt = self._read_ptr(obj_ptr)
            if vmt == 0:
                return None
            name_ptr = self._read_ptr(vmt + VMT_CLASS_NAME)
            if name_ptr == 0:
                return None
            # ShortString: length byte then ASCII chars
            length = self._pm.read_bytes(name_ptr, 1)[0]
            if length == 0 or length > 255:
                return None
            data = self._pm.read_bytes(name_ptr + 1, length)
            return data.decode("ascii", errors="replace")
        except Exception:
            return None

    def _read_unicode_string(self, str_ptr_addr: int) -> Optional[str]:
        """Read a Delphi UnicodeString from a field containing a string ptr.

        UnicodeString layout: length (in chars) at ptr-4, UTF-16LE data at ptr.
        """
        try:
            ptr = self._read_ptr(str_ptr_addr)
            if ptr == 0:
                return ""
            length = struct.unpack("<I", self._pm.read_bytes(ptr - 4, 4))[0]
            if length == 0 or length > 65536:
                return None
            data = self._pm.read_bytes(ptr, length * 2)
            return data.decode("utf-16-le", errors="replace")
        except Exception:
            return None

    # ------------------------------------------------------------------
    # Public state-reading methods
    # ------------------------------------------------------------------

    def is_analysis_running(self) -> Optional[bool]:
        """Check if analysis is currently running.

        Reads TimerAnalyzing.FEnabled: True when analysis timer is active.
        Returns True/False, or None if the read fails.
        """
        addr = self._follow_chain("analysis_running")
        if addr is None:
            return None
        try:
            val = self._pm.read_bytes(addr, 1)[0]
            return val != 0
        except Exception:
            return None

    def get_current_file(self) -> Optional[str]:
        """Get the path of the currently loaded match file."""
        addr = self._follow_chain("current_file_path")
        if addr is None:
            return None
        return self._read_unicode_string(addr)

    def is_match_loaded(self) -> Optional[bool]:
        """Check if a match file is currently loaded.

        Returns True if CurrentFilePath is a non-empty string.
        """
        path = self.get_current_file()
        if path is None:
            return None
        return len(path) > 0

    def get_status_text(self) -> Optional[str]:
        """Read the window title text (contains status info).

        Falls back to Win32 GetWindowTextW since StatusBar has no HWND.
        """
        try:
            buf = ctypes.create_unicode_buffer(512)
            user32.GetWindowTextW(self._hwnd, buf, 512)
            return buf.value
        except Exception:
            return None

    def is_timer_progress_active(self) -> Optional[bool]:
        """Check if the progress timer is active."""
        addr = self._follow_chain("timer_progress_enabled")
        if addr is None:
            return None
        try:
            val = self._pm.read_bytes(addr, 1)[0]
            return val != 0
        except Exception:
            return None

    def read_field(self, key: str) -> Optional[Any]:
        """Generic field reader using the address map.

        Supports types: bool, int32, uint32, int16, byte,
        unicode_string, component_ptr.
        """
        addr = self._follow_chain(key)
        if addr is None:
            return None

        field_type = self._address_map.get_type(key)

        try:
            if field_type == "bool":
                return self._pm.read_bytes(addr, 1)[0] != 0
            elif field_type == "int32":
                return struct.unpack("<i", self._pm.read_bytes(addr, 4))[0]
            elif field_type == "uint32":
                return struct.unpack("<I", self._pm.read_bytes(addr, 4))[0]
            elif field_type == "int16":
                return struct.unpack("<h", self._pm.read_bytes(addr, 2))[0]
            elif field_type == "byte":
                return self._pm.read_bytes(addr, 1)[0]
            elif field_type == "unicode_string":
                return self._read_unicode_string(addr)
            elif field_type == "component_ptr":
                return self._read_ptr(addr)
            else:
                log.warning("Unknown field type: %s", field_type)
                return None
        except Exception:
            return None

    def read_component_class(self, key: str) -> Optional[str]:
        """Read the class name of a component referenced by key."""
        ptr = self.read_field(key)
        if not ptr or not isinstance(ptr, int):
            return None
        return self._read_class_name(ptr)
