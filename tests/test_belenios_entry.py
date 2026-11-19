# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from belenios_demo import bundle


class BeleniosEntryTests(unittest.TestCase):
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
