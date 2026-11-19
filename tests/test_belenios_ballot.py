# SPDX-License-Identifier: GPL-3.0-only
import hashlib
import json
import os
from pathlib import Path
import pty
import select
import shutil
import subprocess
import sys
import tempfile
import termios
import time
import unittest

import belenios_demo as demo
from citizen import synthetic_identity


@unittest.skipUnless(os.environ.get("BELENIOS_TOOL"), "needs the pinned native Belenios tool")
class IndependentVoter(unittest.TestCase):
    def test_voter_prepares_at_home_and_checks_the_count_after_closure(self):
        tool = demo.Tool(os.environ["BELENIOS_TOOL"])
        cli = [sys.executable, "-B", str(Path(demo.__file__).parent / "citizen.py")]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            authority, voter, other = (root / name for name in ("authority", "voter", "other-election"))
            for role in (authority, voter, other):
                role.mkdir(mode=0o700)
            people = [synthetic_identity(n) for n in range(1, 5)]
            archive, credentials = demo.setup(tool, authority, people)
            _, unrelated = demo.setup(tool, other, people)
            initial = voter / "initial.bel"
            shutil.copyfile(archive, initial)
            pin = hashlib.sha256(initial.read_bytes()).hexdigest()

            voter_cli, voter_setup, voter_tool = cli, str(initial), tool.path
            isolation = os.environ.get("CITIZEN_TEST_ISOLATED_VOTER")
            if isolation:
                # Only public program files, the pinned tool and the voter directory enter.
                code = Path(demo.__file__).parent
                wrapper = ["sudo", "-n", "bwrap"] if isolation == "sudo" else ["bwrap"]
                voter_cli = wrapper + ["--unshare-net", "--unshare-pid", "--unshare-ipc", "--unshare-uts",
                    "--die-with-parent", "--uid", str(os.getuid()), "--gid", str(os.getgid()), "--cap-drop", "ALL",
                    "--ro-bind", "/usr", "/usr", "--symlink", "usr/lib", "/lib", "--symlink", "usr/lib64", "/lib64",
                    "--symlink", "usr/bin", "/bin", "--dev", "/dev", "--proc", "/proc", "--tmpfs", "/tmp",
                    "--ro-bind", str(code / "citizen.py"), "/app/citizen.py",
                    "--ro-bind", str(code / "belenios_demo.py"), "/app/belenios_demo.py",
                    "--ro-bind", str(code / "integrations"), "/app/integrations",
                    "--ro-bind", str(Path(tool.path).parent), "/runtime",
                    "--bind", str(voter), "/voter", "--chdir", "/voter", "--", "/usr/bin/python3", "-B", "/app/citizen.py"]
                voter_setup, voter_tool = "/voter/initial.bel", "/runtime/belenios-tool"

            def prepare(person, choice, credential, sha=pin, terminal=False):
                cmd = voter_cli + ["belenios-ballot", voter_setup, "--setup-sha256", sha,
                             "--output", person, "--tool", voter_tool]
                if terminal:
                    master, slave = pty.openpty()
                    try:
                        with subprocess.Popen(cmd, cwd=voter, stdin=slave, stderr=slave, stdout=subprocess.PIPE,
                                              start_new_session=True) as child:
                            try:
                                transcript = b""
                                for prompt, value in ((b"Choose yes, no or abstain (hidden): ", choice),
                                                      (b"Private Belenios credential (hidden): ", credential)):
                                    end = time.monotonic() + 15
                                    while prompt not in transcript:
                                        self.assertTrue(select.select([master], [], [], max(0, end - time.monotonic()))[0],
                                                        "private voter prompt unavailable")
                                        transcript += os.read(master, 4096)
                                    self.assertFalse(termios.tcgetattr(slave)[3] & termios.ECHO)
                                    os.write(master, (value + "\n").encode())
                                out, _ = child.communicate(timeout=30)
                                return subprocess.CompletedProcess(cmd, child.returncode, out.decode(), transcript.decode())
                            finally:
                                if child.poll() is None:
                                    child.kill()
                    finally:
                        os.close(master)
                        os.close(slave)
                return subprocess.run(cmd, cwd=voter, input=choice + "\n" + credential + "\n",
                                      text=True, capture_output=True, timeout=30)

            wrong_setup = prepare("substituted", "yes", credentials[people[0]], "0" * 64)
            self.assertNotEqual(wrong_setup.returncode, 0)
            self.assertNotIn("Private Belenios credential", wrong_setup.stderr)
            invalid = prepare("unregistered", "yes", unrelated[people[0]])
            self.assertNotEqual(invalid.returncode, 0)
            self.assertNotIn(unrelated[people[0]], invalid.stderr + invalid.stdout)
            self.assertFalse((voter / "unregistered").exists())
            self.assertFalse((voter / "substituted").exists())

            receipts = []
            for person, choice in zip(people, ("no", "abstain", "yes", "no")):
                result = prepare(person, choice, credentials[person], terminal=person == people[0])
                self.assertEqual(result.returncode, 0, result.stderr)
                receipt = json.loads(result.stdout)
                self.assertIn(demo.QUESTION["question"], result.stderr)
                self.assertFalse(receipt["submitted"])
                ballot = (voter / person).read_bytes()
                self.assertNotIn(credentials[person].encode(), ballot)
                self.assertNotIn(credentials[person], result.stdout + result.stderr)
                self.assertNotIn("choice", json.loads(ballot))
                if person != people[-1]:
                    tool(authority, "archive", "add-event", "--type", "Ballot", data=ballot)
                receipts.append(receipt)
            original = (voter / people[0]).read_bytes()
            self.assertNotEqual(prepare(people[0], "yes", credentials[people[0]]).returncode, 0)
            self.assertEqual((voter / people[0]).read_bytes(), original)
            tool(authority, "archive", "add-event", "--type", "EndBallots")
            encrypted = tool(authority, "election", "compute-encrypted-tally")
            tool(authority, "archive", "add-event", "--type", "EncryptedTally", data=encrypted)
            key, = authority.glob("*.privkey")
            share = tool(authority, "election", "decrypt", "--privkey", key.name, "--trustee-id", "1")
            tool(authority, "archive", "add-event", "--type", "PartialDecryption", data=share)
            result = tool(authority, "election", "compute-result")
            tool(authority, "archive", "add-event", "--type", "Result", data=result)
            closed = voter / "closed.bel"
            shutil.copyfile(archive, closed)
            shutil.rmtree(authority)
            for index, receipt in enumerate(receipts):
                cmd = cli + ["belenios-tally", str(initial), str(closed), "--setup-sha256", pin,
                             "--eligible", "6", "--tool", tool.path, "--ballot-sha256", receipt["ballot_sha256"]]
                tally = json.loads(subprocess.check_output(cmd, cwd=voter))
                self.assertEqual(tally["ballot_included"], index < 3)
                self.assertEqual([tally[k] for k in ("yes", "no", "abstain", "not_voted")], [1, 1, 1, 3])
            self.assertEqual(hashlib.sha256(initial.read_bytes()).hexdigest(), pin)
