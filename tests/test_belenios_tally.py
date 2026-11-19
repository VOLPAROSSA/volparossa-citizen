# SPDX-License-Identifier: GPL-3.0-only
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import belenios_demo as demo
from citizen import Choice, synthetic_identity
from integrations.belenios.tally import tally


@unittest.skipUnless(os.environ.get("BELENIOS_TOOL"), "needs the pinned native Belenios tool")
class NativeTally(unittest.TestCase):
    def test_independent_question_and_denominator(self):
        tool = demo.Tool(os.environ["BELENIOS_TOOL"])
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            work = root / "casting"
            work.mkdir()
            people = [synthetic_identity(i) for i in range(1, 5)]
            question = "Plant trees in the fictional schoolyard?"
            with patch.dict(demo.QUESTION, question=question):
                archive, credentials = demo.setup(tool, work, people)
            initial = root / "initial.bel"
            shutil.copyfile(archive, initial)
            pin = hashlib.sha256(initial.read_bytes()).hexdigest()
            for voter in people[:3]:
                demo.cast(tool, work, credentials[voter], Choice.YES)
            tool(work, "archive", "add-event", "--type", "EndBallots")
            encrypted = tool(work, "election", "compute-encrypted-tally")
            tool(work, "archive", "add-event", "--type", "EncryptedTally", data=encrypted)
            key, = work.glob("*.privkey")
            partial = tool(work, "election", "decrypt", "--privkey", key.name, "--trustee-id", "1")
            tool(work, "archive", "add-event", "--type", "PartialDecryption", data=partial)
            altered = root / "altered"
            altered.mkdir()
            shutil.copyfile(archive, altered / archive.name)
            result = tool(work, "election", "compute-result")
            tool(work, "archive", "add-event", "--type", "Result", data=result)
            tool(altered, "archive", "add-event", "--type", "Result", data=b'{"result":[[0,3,0]]}')
            final = root / "closed.bel"
            shutil.copyfile(archive, final)
            shutil.rmtree(work)
            report = tally(tool.path, initial, final, pin, 4)
            self.assertEqual((report["question"], report["verified_ballots"], report["outcome"]),
                             (question, 3, "adopted"))
            command = [sys.executable, "-B", str(Path(demo.__file__).parent / "citizen.py"), "belenios-tally",
                       str(initial), str(final), "--setup-sha256", pin, "--eligible", "5", "--tool", tool.path]
            other = json.loads(subprocess.check_output(command))
            self.assertEqual([other[k] for k in ("public_credentials", "yes", "no", "abstain", "not_voted",
                                                 "decision_required", "outcome")], [4, 3, 0, 0, 2, 4, "indeterminate"])
            with self.assertRaisesRegex(ValueError, "eligible|credentials"):
                tally(tool.path, initial, final, pin, 3)
            with self.assertRaisesRegex(ValueError, "independent setup"):
                tally(tool.path, initial, final, "0" * 64, 4)
            with self.assertRaisesRegex(ValueError, "Belenios operation failed"):
                tally(tool.path, initial, altered / archive.name, pin, 4)
