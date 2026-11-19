# SPDX-License-Identifier: GPL-3.0-only
"""Prepare one encrypted Belenios ballot on the fictional voter's Linux machine."""
from contextlib import contextmanager
import getpass
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import warnings

from belenios_demo import Tool
from citizen import Choice, MAX_IDENTITIES, require
from integrations.belenios.tally import archive_copy, read_setup


def private_line(prompt):
    if sys.stdin.isatty():
        # getpass normally falls back to visible input if the terminal cannot hide it.
        with warnings.catch_warnings():
            warnings.simplefilter("error", getpass.GetPassWarning)
            try:
                return getpass.getpass(prompt)
            except (getpass.GetPassWarning, EOFError) as error:
                raise ValueError("private terminal input unavailable") from error
    print(prompt, end="", file=sys.stderr, flush=True)
    value = sys.stdin.readline(1025)
    require(value.endswith("\n") and len(value) <= 1024, "expected one private input line")
    return value.rstrip("\r\n")


@contextmanager
def anonymous_input(value):
    with os.fdopen(os.memfd_create("citizen-input"), "w+b") as stream:
        stream.write(value)
        stream.seek(0)
        yield stream.fileno()


def prepare_ballot(executable, source, setup_sha256, output):
    require(isinstance(setup_sha256, str), "expected an independent SHA-256 setup digest")
    require(hasattr(os, "memfd_create") and Path("/proc/self/fd").is_dir(), "private voter input requires Linux")
    target = Path(output)
    require(not os.path.lexists(target), "ballot output already exists")
    tool = Tool(executable)
    with tempfile.TemporaryDirectory() as directory:
        work = Path(directory)
        archive_copy(source, work / "election.bel", setup_sha256)
        require(tool(work, "--version").split()[:1] == [b"3.3.0"], "requires Belenios 3.3.0")
        tool(work, "election", "verify")
        _, election, question = read_setup(tool, work, MAX_IDENTITIES)
        # Escape control characters in externally supplied election text on a terminal.
        print("Election", json.dumps(election["name"]), file=sys.stderr)
        print("Question", json.dumps(question["question"]), file=sys.stderr)
        choice = private_line("Choose yes, no or abstain (hidden): ").strip().lower()
        require(choice in [option.value for option in Choice], "choose yes, no or abstain")
        credential = private_line("Private Belenios credential (hidden): ").strip()
        require(re.fullmatch(r"[A-Za-z0-9-]{1,256}", credential), "invalid private credential format")
        selection = json.dumps([[int(option.value == choice) for option in Choice]]).encode()
        with anonymous_input(selection) as answer, anonymous_input((credential + "\n").encode()) as secret:
            ballot = tool(work, "election", "generate-ballot",
                          "--choice", f"/proc/self/fd/{answer}",
                          "--privcred", f"/proc/self/fd/{secret}", pass_fds=(answer, secret))
        # Verify the encrypted ballot and its membership before offering it for submission.
        tool(work, "archive", "add-event", "--type", "Ballot", data=ballot)
        tool(work, "election", "verify")
        summary = json.loads(tool(work, "election", "compute-ballot-summary"))
        require(len(summary) == 1 and re.fullmatch(r"[0-9a-f]{64}", summary[0]["hash"]), "missing verified ballot tracker")
        with tempfile.NamedTemporaryFile(dir=target.parent) as tmp:
            tmp.write(ballot)
            tmp.flush()
            os.fsync(tmp.fileno())
            os.link(tmp.name, target)
        return {"encrypted_ballot": str(target), "ballot_sha256": summary[0]["hash"], "submitted": False}
