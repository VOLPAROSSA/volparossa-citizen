# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import json
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from belenios_demo import bundle
from integrations.belenios.replay import verify_cached


class BeleniosEntryTests(unittest.TestCase):
    def test_core_receipt_must_bind_the_publisher_and_temp_file_is_removed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pin = root / "setup.json"
            pin.write_text("{}")
            key = "42" * 32
            outputs = []

            def assemble(argv, **_):
                output = Path(argv[argv.index("--output") + 1])
                output.write_bytes(b"test")
                outputs.append(output)
                return json.dumps({"operation": "offline_content_assemble", "network_retrieval": False,
                                   "publisher_key_hex": "43" * 32, "bytes": 4, "output": str(output)})

            with patch("integrations.belenios.replay.subprocess.check_output", side_effect=assemble), \
                 patch("integrations.belenios.replay.verify") as verifier:
                with self.assertRaisesRegex(ValueError, "publisher-bound"):
                    verify_cached("core", "belenios", root / "manifest", key, [root], pin)
                verifier.assert_not_called()
            self.assertEqual(len(outputs), 1)
            self.assertFalse(outputs[0].parent.exists())

    def test_missing_external_tool_leaves_no_bundle(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "public.zip"
            run = subprocess.run([sys.executable, "-B", "citizen.py", "belenios-demo",
                                  "--tool", str(Path(tmp) / "missing"), "--public-bundle", out],
                                 cwd=Path(__file__).resolve().parents[1], capture_output=True)
            self.assertNotEqual(run.returncode, 0)
            self.assertIn(b"Belenios 3.3.0 executable unavailable", run.stderr)
            self.assertFalse(out.exists())

    def test_publication_preserves_existing_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            public = Path(tmp)
            (public / "report.json").write_text("{}")
            existing = public / "previous.zip"
            existing.write_bytes(b"previous bundle")
            with self.assertRaises(FileExistsError):
                bundle(public, existing)
            self.assertEqual(existing.read_bytes(), b"previous bundle")
