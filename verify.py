import io
from contextlib import redirect_stdout
from pathlib import Path
import unittest

import joint_inputs


def main() -> int:
    try:
        with redirect_stdout(io.StringIO()):
            joint_inputs.main()
    except Exception as error:
        print(f'joint sample fixture check failed: {error}')
        return 1
    tests = Path(__file__).resolve().parent / 'tests'
    suite = unittest.defaultTestLoader.discover(str(tests))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() and result.testsRun else 1


if __name__ == '__main__':
    raise SystemExit(main())
