"""Test package marker.

Pytest + xdist can import test modules via importlib; making `tests` a real package
keeps relative imports inside the test suite stable across workers.
"""
