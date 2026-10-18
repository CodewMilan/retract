from pathlib import Path
import tempfile
import tomllib
import unittest

from scripts.configure_codex import prepare, settings, toml_value


class ConfigurationTests(unittest.TestCase):
    def test_generated_toml_is_portable_to_paths_with_spaces_and_quotes(self):
        with tempfile.TemporaryDirectory(prefix="retract config ") as directory:
            root = Path(directory) / "quoted ' project"
            import sys
            python = root / ".venv/bin/python"
            python.parent.mkdir(parents=True)
            python.symlink_to(sys.executable)
            config = settings(root, python, "http://127.0.0.1:8100", root / "reports")
            self.assertEqual(config["command"], str(python.absolute()))
            parsed = tomllib.loads("server = " + toml_value(config))["server"]
            self.assertEqual(parsed, config)
            self.assertEqual(parsed["env"]["RETRACT_URL"], "http://127.0.0.1:8100")
            self.assertEqual(set(parsed["enabled_tools"]), {"remember", "process_update", "recall", "history", "record_plan", "revise_plan", "handoff", "claim_handoff"})

    def test_prepare_writes_reviewable_files_and_does_not_claim_an_agent_call(self):
        import sys
        with tempfile.TemporaryDirectory() as directory:
            result = prepare(Path(directory), python=Path(sys.executable), api_url="http://127.0.0.1:8100")
            self.assertFalse(result["user_settings_modified"])
            self.assertFalse(result["coding_client_recall_observed"])
            self.assertEqual(result["configuration_recognized"], "not_checked")
            config = tomllib.loads(Path(result["configuration"]).read_text())
            self.assertEqual(config["mcp_servers"]["retract"]["required"], True)
            script = Path(result["launch_script"]).read_text()
            self.assertIn("codex exec --json", script)
            self.assertIn("AGENT_TASK.md", script)
            self.assertNotIn("dangerously-bypass", script)
