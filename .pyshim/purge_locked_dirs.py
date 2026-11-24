"""Remove directories the sandbox left with a restrictive (0o700) DACL.

Created by an earlier run before the mkdir/tempfile patch in sitecustomize.py.
Those directories deny even the owning token, so plain rmtree cannot touch
them; re-applying an open mode first usually clears the deny.
"""

import os
import shutil
import sys
import stat


def unlock(path):
    for mode in (0o777, stat.S_IRWXU):
        try:
            os.chmod(path, mode)
            return True
        except Exception:
            continue
    return False


def purge(root):
    removed = stuck = 0
    for name in os.listdir(root):
        target = os.path.join(root, name)
        for dirpath, dirnames, filenames in os.walk(target, topdown=False):
            for item in dirnames + filenames:
                unlock(os.path.join(dirpath, item))
            unlock(dirpath)
        unlock(target)
        try:
            shutil.rmtree(target)
            removed += 1
        except Exception as exc:
            stuck += 1
            print("stuck:", name, type(exc).__name__)
    return removed, stuck


if __name__ == "__main__":
    root = sys.argv[1] if len(sys.argv) > 1 else os.getcwd()
    if not os.path.isdir(root):
        print("not a directory:", root)
        raise SystemExit(1)
    removed, stuck = purge(root)
    print("removed", removed, "stuck", stuck)
    try:
        os.rmdir(root)
        print("root removed")
    except Exception as exc:
        print("root kept:", type(exc).__name__)
