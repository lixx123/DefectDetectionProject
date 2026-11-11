# Phase12 build environment

Windows: Windows-11-10.0.26200-SP0

Python: 3.14.7

PyInstaller: 6.22.3

pyinstaller-hooks-contrib: 2026.9

PySide6: 6.12.0

numpy: 2.5.4

opencv-python: 5.0.0.93

PyYAML: 6.0.3

Fixed build dependencies: packaging/requirements-build.txt; runtime versions: requirements-lock.txt.

Qt statistics use QPainter, not matplotlib. External frozen detection environment is excluded by explicit user authorization.

Supported and actually tested OS: Windows 11 x64. Qt uses Windows system ICU; do not bundle unrelated PATH ICU (observed Poppler ICU symbol mismatch). Other Windows versions require separate deployment validation.
