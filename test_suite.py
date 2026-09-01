import os
import sys

# Add src and tests to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), 'src')))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), 'tests')))

import pytest

if __name__ == "__main__":
    sys.exit(pytest.main(["tests"]))
