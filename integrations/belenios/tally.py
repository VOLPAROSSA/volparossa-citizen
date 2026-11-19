# SPDX-License-Identifier: GPL-3.0-only
"""Read a closed public Belenios referendum using a separately retained setup."""
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import tarfile
import tempfile

from belenios_demo import Tool
from citizen import MAX_IDENTITIES, referendum_outcome, require


def verified_tally(tool, initial, final, eligible):
    """Both directories contain private copies of the public election.bel inputs."""
    require(type(eligible) is int and 1 <= eligible <= MAX_IDENTITIES, "unsupported eligible population")
    tool(final, "election", "verify-diff", "--dir1", str(initial), "--dir2", str(final))
    setup = json.loads(tool(initial, "election", "compute-checksums"))
    closed = json.loads(tool(final, "election", "compute-checksums"))
    require(not setup.get("encrypted_tally") and not setup.get("final")
            and json.loads(tool(initial, "election", "compute-ballot-summary")) == [],
            "expected an initial setup before voting")
    require(closed.get("final") and closed.get("encrypted_tally") and all(closed.get(k) == v for k, v in setup.items()),
            "the final archive must close the original election")
    with tarfile.open(initial / "election.bel", "r:") as archive:
        def data(digest):
            require(isinstance(digest, str) and re.fullmatch(r"[0-9a-f]{64}", digest), "invalid Belenios checksum")
            member = archive.getmember(digest + ".data.json")
            require(member.isfile() and member.size <= 1024 * 1024, "unexpected setup record")
            raw = archive.extractfile(member).read()
            require(hashlib.sha256(raw).hexdigest() == digest, "setup data differs from checksum")
            return json.loads(raw)

        election = data(setup["election"])
        credentials = data(setup["public_credentials"])
    require(isinstance(credentials, list) and type(setup["num_voters"]) is int
            and len(credentials) == setup["num_voters"] and 1 <= len(credentials) <= eligible
            and all(isinstance(key, str) and re.fullmatch(r"[0-9a-f]{64}", key) for key in credentials)
            and len(set(credentials)) == len(credentials), "expected distinct unweighted public credentials")
    questions = election["questions"]
    require(election.get("group") == "Ed25519" and len(questions) == 1 and isinstance(questions[0], dict),
            "expected a single Ed25519 referendum question")
    question = questions[0]
    require(set(question) == {"min", "max", "question", "answers"} and type(question["min"]) is int
            and type(question["max"]) is int and question["min"] == question["max"] == 1
            and question["answers"] == ["Yes", "No", "Abstain"]
            and isinstance(question["question"], str) and question["question"].strip(),
            "expected one Yes, No or Abstain answer per ballot")
    rows = json.loads(tool(final, "election", "compute-result"))["result"]
    ballots = json.loads(tool(final, "election", "compute-ballot-summary"))
    require(isinstance(rows, list) and len(rows) == 1 and isinstance(rows[0], list) and len(rows[0]) == 3
            and all(type(n) is int and n >= 0 for n in rows[0]) and isinstance(ballots, list)
            and sum(rows[0]) == len(ballots) <= len(credentials), "ballots and unweighted tally differ")
    yes, no, abstain = rows[0]
    return {"election_name": election["name"], "question": question["question"], "declared_eligible": eligible, "public_credentials": len(credentials),
            "verified_ballots": len(ballots), "yes": yes, "no": no, "abstain": abstain,
            "not_voted": eligible - len(ballots), "decision_required": (2 * eligible + 2) // 3,
            "outcome": referendum_outcome(yes, no, eligible).value}


def tally(executable, initial, final, setup_sha256, eligible):
    require(re.fullmatch(r"[0-9a-fA-F]{64}", setup_sha256), "expected an independent SHA-256 setup digest")
    require(type(eligible) is int and 1 <= eligible <= MAX_IDENTITIES, "unsupported eligible population")
    tool = Tool(executable)
    with tempfile.TemporaryDirectory() as scratch:
        work = Path(scratch)
        require(tool(work, "--version").split()[:1] == [b"3.3.0"], "requires Belenios 3.3.0")
        for directory, source in (("setup", initial), ("final", final)):
            parent = work / directory
            parent.mkdir()
            destination = parent / "election.bel"
            limit = 64 * 1024 * 1024
            with os.fdopen(os.open(source, os.O_RDONLY | os.O_NONBLOCK), "rb") as stream, destination.open("xb") as output:
                info = os.fstat(stream.fileno())
                require(stat.S_ISREG(info.st_mode) and 0 < info.st_size <= limit, "expected a regular public archive up to 64 MiB")
                digest = hashlib.sha256()
                total = 0
                while chunk := stream.read(1024 * 1024):
                    total += len(chunk)
                    require(total <= limit, "public archive exceeds 64 MiB")
                    digest.update(chunk)
                    output.write(chunk)
            if directory == "setup":
                require(digest.hexdigest() == setup_sha256.lower(), "initial archive differs from the independent setup digest")
        return verified_tally(tool, work / "setup", work / "final", eligible)
