"""Documentation must not contain broken links.

The doc sets cross-reference each other by relative path and by heading anchor,
so a renamed page or heading silently breaks the reader's navigation. This test
runs `tools/check_docs.py` over the whole `docs/` tree.
"""

import subprocess
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


class DocumentationLinkTests(unittest.TestCase):
    def test_no_broken_links_or_anchors(self):
        result = subprocess.run(
            [sys.executable, str(REPO_ROOT / "tools" / "check_docs.py")],
            capture_output=True, text=True, cwd=REPO_ROOT)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_mkb_language_pages_are_reachable(self):
        index = (REPO_ROOT / "docs" / "README.md").read_text(encoding="utf-8")
        for page in ("syntax.md", "modules.md", "functions.md", "usage.md",
                     "reference/commons.md"):
            self.assertIn(f"mkb-language/{page}", index, page)


if __name__ == "__main__":
    unittest.main()
