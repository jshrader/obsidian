import sys
import unittest
from datetime import date
from pathlib import Path

import frontmatter

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from blog_publish import extract_last_updated


class LastUpdatedFrontmatterTests(unittest.TestCase):
    def test_last_updated_serializes_as_unquoted_yaml_date(self):
        body = """
Some body text.

<p>Version history<br>
2026-04-20: First draft<br>
2026-04-22: Revised</p>
"""
        last_updated = extract_last_updated(body, "2026-04-01 09:30")

        self.assertEqual(last_updated, date(2026, 4, 22))

        dumped = frontmatter.dumps(frontmatter.Post("Body", last_updated=last_updated))
        self.assertIn("last_updated: 2026-04-22\n", dumped)
        self.assertNotIn("last_updated: '2026-04-22'\n", dumped)


if __name__ == "__main__":
    unittest.main()
