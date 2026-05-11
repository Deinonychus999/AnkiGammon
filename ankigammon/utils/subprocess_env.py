"""Subprocess environment helpers.

External binaries launched from a PyInstaller-frozen build inherit the
bootloader's modified ``LD_LIBRARY_PATH`` (and ``DYLD_*`` on macOS), which
points into the bundle's extracted lib directory and can break system
binaries like ``gnubg``. The helper here restores the caller's original
environment so external tools see a clean linker path.
"""

import os
import sys


def external_subprocess_env() -> dict:
    """Environment for launching external binaries from a frozen build.

    PyInstaller's bootloader prepends its extraction dir to LD_LIBRARY_PATH
    (and the DYLD_* equivalents on macOS) so the bundled Python finds its
    own libs, and stashes the caller's original value in ``*_ORIG``. Child
    processes inherit the modified path, which causes system binaries like
    ``gnubg`` to load the AppImage's bundled libs and fail with cryptic
    errors (or just non-zero exit and empty stderr). Restore the original
    values so external tools see a clean environment.

    No-op outside a PyInstaller-frozen build — we must not strip a user's
    legitimate LD_LIBRARY_PATH when running from pip / source.
    """
    env = os.environ.copy()
    if not getattr(sys, 'frozen', False):
        return env
    for var in (
        'LD_LIBRARY_PATH',
        'DYLD_LIBRARY_PATH',
        'DYLD_FRAMEWORK_PATH',
        'DYLD_FALLBACK_LIBRARY_PATH',
        'DYLD_FALLBACK_FRAMEWORK_PATH',
    ):
        orig = env.pop(var + '_ORIG', None)
        if orig is not None:
            env[var] = orig
        else:
            env.pop(var, None)
    return env
