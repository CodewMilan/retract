import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from retract.cli import load_env_file


class EnvFileTests(unittest.TestCase):
    def test_env_file_fills_missing_values_without_overriding_exports(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / ".env"
            path.write_text("# comment\nRETRACT_TEST_A=from-file\nRETRACT_TEST_B='quoted'\n"
                            "RETRACT_TEST_EMPTY=\nRETRACT_TEST_EXPORTED=from-file\nnot a pair\n")
            with patch.dict(os.environ, {"RETRACT_TEST_EXPORTED": "exported"}):
                load_env_file(path)
                self.assertEqual(os.environ["RETRACT_TEST_A"], "from-file")
                self.assertEqual(os.environ["RETRACT_TEST_B"], "quoted")
                self.assertNotIn("RETRACT_TEST_EMPTY", os.environ)
                self.assertEqual(os.environ["RETRACT_TEST_EXPORTED"], "exported")

    def test_missing_env_file_is_ignored(self):
        load_env_file(Path(tempfile.gettempdir()) / "retract-no-such-dir" / ".env")


if __name__ == "__main__":
    unittest.main()
