from pathlib import Path
import unittest


def main() -> int:
    tests = Path(__file__).resolve().parent / 'tests'
    suite = unittest.defaultTestLoader.discover(str(tests))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() and result.testsRun else 1


if __name__ == '__main__':
    raise SystemExit(main())
