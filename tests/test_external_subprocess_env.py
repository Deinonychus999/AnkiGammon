"""Regression tests for external_subprocess_env().

PyInstaller-frozen builds prepend their extraction dir to LD_LIBRARY_PATH
(and DYLD_* on macOS), which leaks into child processes and breaks external
binaries like gnubg. The helper restores the caller's original environment
when frozen, and is a no-op otherwise.
"""

import os
import sys
from unittest import mock

from ankigammon.utils.subprocess_env import external_subprocess_env


def _frozen():
    return mock.patch.object(sys, 'frozen', True, create=True)


def test_restores_ld_library_path_from_orig():
    """When PyInstaller has stashed an _ORIG copy, restore it."""
    fake_env = {
        'LD_LIBRARY_PATH': '/tmp/_MEI12345/lib',
        'LD_LIBRARY_PATH_ORIG': '/usr/lib:/usr/local/lib',
        'PATH': '/usr/bin',
    }
    with _frozen(), mock.patch.dict(os.environ, fake_env, clear=True):
        env = external_subprocess_env()

    assert env['LD_LIBRARY_PATH'] == '/usr/lib:/usr/local/lib'
    assert 'LD_LIBRARY_PATH_ORIG' not in env
    assert env['PATH'] == '/usr/bin'


def test_strips_ld_library_path_when_no_orig_and_frozen():
    """When frozen and LD_LIBRARY_PATH is set without _ORIG, drop it.

    PyInstaller always stashes _ORIG when it modifies the var, so the
    absence of _ORIG means the caller had nothing set originally —
    strip the var so the child sees a clean env.
    """
    fake_env = {
        'LD_LIBRARY_PATH': '/tmp/_MEI12345/lib',
        'PATH': '/usr/bin',
    }
    with _frozen(), mock.patch.dict(os.environ, fake_env, clear=True):
        env = external_subprocess_env()

    assert 'LD_LIBRARY_PATH' not in env
    assert env['PATH'] == '/usr/bin'


def test_passthrough_when_not_frozen_preserves_user_ld_library_path():
    """Running from pip / source must NOT strip the user's LD_LIBRARY_PATH.

    A user who built gnubg with deps in a non-standard prefix may have set
    LD_LIBRARY_PATH in their shell. Stripping it would silently break the
    pip-installed version, which is precisely the case where there's no
    PyInstaller pollution to clean up.
    """
    fake_env = {
        'LD_LIBRARY_PATH': '/opt/custom-gnubg/lib',
        'PATH': '/usr/bin',
        'HOME': '/home/user',
    }
    with mock.patch.object(sys, 'frozen', False, create=True):
        with mock.patch.dict(os.environ, fake_env, clear=True):
            env = external_subprocess_env()

    assert env == fake_env


def test_handles_all_dyld_variants_when_frozen():
    """All DYLD_* variants used by PyInstaller on macOS get restored."""
    fake_env = {
        'DYLD_LIBRARY_PATH': '/tmp/_MEI/lib',
        'DYLD_LIBRARY_PATH_ORIG': '/usr/lib',
        'DYLD_FRAMEWORK_PATH': '/tmp/_MEI/Frameworks',
        'DYLD_FRAMEWORK_PATH_ORIG': '/Library/Frameworks',
        'DYLD_FALLBACK_LIBRARY_PATH': '/tmp/_MEI/lib',
        'DYLD_FALLBACK_FRAMEWORK_PATH': '/tmp/_MEI/Frameworks',
    }
    with _frozen(), mock.patch.dict(os.environ, fake_env, clear=True):
        env = external_subprocess_env()

    assert env['DYLD_LIBRARY_PATH'] == '/usr/lib'
    assert env['DYLD_FRAMEWORK_PATH'] == '/Library/Frameworks'
    assert 'DYLD_FALLBACK_LIBRARY_PATH' not in env
    assert 'DYLD_FALLBACK_FRAMEWORK_PATH' not in env
    assert not any(k.endswith('_ORIG') for k in env)


def test_does_not_mutate_os_environ():
    """The helper must not mutate the real process environment."""
    fake_env = {
        'LD_LIBRARY_PATH': '/tmp/_MEI/lib',
        'LD_LIBRARY_PATH_ORIG': '/usr/lib',
    }
    with _frozen(), mock.patch.dict(os.environ, fake_env, clear=True):
        external_subprocess_env()
        assert os.environ['LD_LIBRARY_PATH'] == '/tmp/_MEI/lib'
        assert os.environ['LD_LIBRARY_PATH_ORIG'] == '/usr/lib'
