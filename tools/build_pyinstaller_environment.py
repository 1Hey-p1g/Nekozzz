"""Keep the observed unrelated JDK CRT copies out of Windows build discovery.

Only the child build environment changes. No application PATH or package
versions change, and no DLL is deleted from an already-built bundle.
"""
import os
import subprocess
import sys

JDK_BIN = r'C:\Program Files\Microsoft\jdk-17.0.8.7-hotspot\bin'


def build_environment(environ):
    result = dict(environ)
    excluded = os.path.normcase(os.path.normpath(JDK_BIN))
    result['PATH'] = os.pathsep.join(entry for entry in result.get('PATH', '').split(os.pathsep)
        if os.path.normcase(os.path.normpath(entry.strip().strip('"'))) != excluded)
    return result


if __name__ == '__main__':
    sys.exit(subprocess.call([sys.executable, *sys.argv[1:]], env=build_environment(os.environ)))
