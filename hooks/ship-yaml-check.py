#!/usr/bin/env python3
"""Read-only YAML syntax check for /ship agents: ship-yaml-check.py <file>..."""
import sys

import yaml

bad = 0
for path in sys.argv[1:]:
    try:
        with open(path) as f:
            yaml.safe_load(f)
        print(f"ok {path}")
    except (OSError, yaml.YAMLError) as e:
        bad = 1
        print(f"FAIL {path}: {e}")
sys.exit(bad)
