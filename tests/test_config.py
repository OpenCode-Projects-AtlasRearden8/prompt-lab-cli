import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import promptlab.config as config


class ConfigTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name) / "lib"
        self.root.mkdir(parents=True)
        self._env = mock.patch.dict(os.environ, {}, clear=False)
        self._env.start()

    def tearDown(self):
        self._env.stop()
        self._tmp.cleanup()

    def test_defaults(self):
        cfg = config.load_config(self.root)
        self.assertEqual(cfg["base_url"], "http://localhost:11434/v1")
        self.assertEqual(cfg["model"], "llama3.2")
        self.assertEqual(cfg["temperature"], 0.7)
        self.assertIsNone(cfg["system"])

    def test_file_overrides_defaults(self):
        (self.root / "config.json").write_text(
            '{"base_url": "http://127.0.0.1:1234/v1", "model": "custom", "timeout": 5}',
            encoding="utf-8",
        )
        cfg = config.load_config(self.root)
        self.assertEqual(cfg["base_url"], "http://127.0.0.1:1234/v1")
        self.assertEqual(cfg["model"], "custom")
        self.assertEqual(cfg["timeout"], 5.0)

    def test_env_overrides_file_and_defaults(self):
        (self.root / "config.json").write_text('{"model": "file-model"}', encoding="utf-8")
        with mock.patch.dict(os.environ, {"PROMPTLAB_MODEL": "env-model", "PROMPTLAB_BASE_URL": "http://x/v1"}):
            cfg = config.load_config(self.root)
        self.assertEqual(cfg["model"], "env-model")
        self.assertEqual(cfg["base_url"], "http://x/v1")

    def test_invalid_json(self):
        (self.root / "config.json").write_text("{nope", encoding="utf-8")
        with self.assertRaises(config.ConfigError):
            config.load_config(self.root)

    def test_bad_temperature(self):
        (self.root / "config.json").write_text('{"temperature": "hot"}', encoding="utf-8")
        with self.assertRaises(config.ConfigError):
            config.load_config(self.root)

    def test_missing_scheme(self):
        with self.assertRaises(config.ConfigError):
            config.validate("localhost:11434/v1", "m")
        base, model = config.validate("http://localhost:11434/v1/", "  m ")
        self.assertEqual((base, model), ("http://localhost:11434/v1", "m"))

    def test_missing_model(self):
        with self.assertRaises(config.ConfigError):
            config.validate("http://localhost:11434/v1", "")

    def test_api_key_in_config_is_rejected(self):
        (self.root / "config.json").write_text('{"api_key": "sk-nope"}', encoding="utf-8")
        with self.assertRaisesRegex(config.ConfigError, "never uses API keys"):
            config.load_config(self.root)

    def test_api_key_in_env_is_rejected(self):
        with mock.patch.dict(os.environ, {"PROMPTLAB_API_KEY": "sk-nope"}):
            with self.assertRaisesRegex(config.ConfigError, "never uses API keys"):
                config.load_config(self.root)

    def test_write_defaults(self):
        path = config.write_defaults(self.root)
        self.assertTrue(path.is_file())
        self.assertIn("localhost:11434", path.read_text(encoding="utf-8"))
        config.write_defaults(self.root)  # idempotent, no rewrite errors


if __name__ == "__main__":
    unittest.main()
