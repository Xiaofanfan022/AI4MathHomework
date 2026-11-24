"""Workspace shim for DSH's Windows file sandbox.

Why this exists
---------------
The sandbox token can create a directory with mode 0o777 / 0o755, but a
directory created with mode 0o700 gets a restrictive DACL that the confined
token cannot write into.  CPython's ``tempfile.mkdtemp`` hardcodes
``os.mkdir(file, 0o700)``, so every ``pip`` scratch directory (pip-unpack,
pip-build-tracker, pip-install, pip-target, pip-ephem-wheel-cache) becomes
read-only for us and pip dies with::

    ERROR: Could not install packages due to an OSError: [Errno 13]
    Permission denied: '...\\pip-unpack-xxxx\\foo.whl.metadata'

``tempfile._resetperms`` has the same problem: it calls ``os.chmod(dir, 0o700)``
which raises ``PermissionError: [WinError 5]`` and breaks ``ensurepip`` /
``python -m venv``.

The shim forces 0o777 for both, which the sandbox accepts.  It is opt-in:
it only takes effect when this directory is on ``PYTHONPATH``.
"""

import os
import sys
import tempfile

# Make the ppt-master dependencies installed into <workspace>\.deps importable.
_DEPS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".deps")
if os.path.isdir(_DEPS) and _DEPS not in sys.path:
    sys.path.append(_DEPS)

if os.name == "nt":
    _OPEN_DIR_MODE = 0o777

    # Generic fix: any ``mkdir`` with a restrictive mode gets an open DACL.
    # Covers pathlib.Path.mkdir(mode=0o700) as used by ppt-master's
    # svg_to_pptx/pptx_package/builder.py:5448 (".pptx-build-*" work dirs).
    _real_mkdir = os.mkdir

    def _mkdir(path, mode=0o777, *, dir_fd=None):
        if mode & 0o077 == 0:
            mode = _OPEN_DIR_MODE
        if dir_fd is None:
            return _real_mkdir(path, mode)
        return _real_mkdir(path, mode, dir_fd=dir_fd)

    os.mkdir = _mkdir

    def _mkdtemp(suffix=None, prefix=None, dir=None):
        """Drop-in replacement for tempfile.mkdtemp using an open DACL."""
        suffix = "" if suffix is None else suffix
        prefix = tempfile.gettempprefix() if prefix is None else prefix
        directory = tempfile.gettempdir() if dir is None else dir
        for name in tempfile._get_candidate_names():
            path = os.path.join(directory, prefix + name + suffix)
            try:
                os.mkdir(path, _OPEN_DIR_MODE)
            except FileExistsError:
                continue
            except PermissionError:
                continue
            return path
        raise FileExistsError(
            "No usable temporary directory name found in %r" % (directory,)
        )

    def _resetperms(path):
        """Drop-in replacement for tempfile._resetperms (mode 0o777)."""
        try:
            os.chmod(path, _OPEN_DIR_MODE, follow_symlinks=False)
        except (NotImplementedError, PermissionError, OSError):
            pass

    tempfile.mkdtemp = _mkdtemp
    tempfile._resetperms = _resetperms
    # Anything that captured the old callable at import time.
    for _mod_name in ("tempfile",):
        _mod = sys.modules.get(_mod_name)
        if _mod is not None:
            _mod.mkdtemp = _mkdtemp
            _mod._resetperms = _resetperms
