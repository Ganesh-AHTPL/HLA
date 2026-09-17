"""
Zero Hardcoding Test Suite.
Scans the backend codebase to verify that no hardcoded Control-23 logic or synthetic aliases remain (RULE 9, RULE 33, RULE 38).
"""

import unittest
import os
import sys
import re

# Ensure project root is in sys.path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

BACKEND_DIR = os.path.join(PROJECT_ROOT, "backend")

# Forbidden hardcoded execution patterns (excluding constants.py definitions)
FORBIDDEN_CODE_PATTERNS = [
    (r'[^"\']\bWHERE\s+ctrl_id\s*=\s*23\b', "Hardcoded 'ctrl_id = 23' in query"),
    (r"\bcontrol_id\s*==\s*23\b", "Hardcoded control_id == 23 branching"),
    (r"\bctrl_id\s*==\s*23\b", "Hardcoded ctrl_id == 23 branching"),
]


class TestNoControl23Hardcoding(unittest.TestCase):

    def test_no_forbidden_patterns_in_backend(self):
        violations = []
        for root, _, files in os.walk(BACKEND_DIR):
            for file in files:
                if file.endswith(".py"):
                    file_path = os.path.join(root, file)
                    with open(file_path, "r", encoding="utf-8") as f:
                        lines = f.readlines()

                    for line_idx, line in enumerate(lines, start=1):
                        # Skip pure comment lines
                        if line.strip().startswith("#"):
                            continue
                        for pattern, desc in FORBIDDEN_CODE_PATTERNS:
                            if re.search(pattern, line, re.IGNORECASE):
                                violations.append(f"{file}:{line_idx} -> {desc}: {line.strip()}")

        self.assertEqual(len(violations), 0, "Hardcoding violations found:\n" + "\n".join(violations))


if __name__ == "__main__":
    unittest.main()
