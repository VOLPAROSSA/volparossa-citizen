# SPDX-License-Identifier: GPL-3.0-only
"""Recheck the three fictional public archive pairs with Belenios 3.3.0."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import tarfile
from zipfile import ZipFile

EXPECTED = {"adopted": [4, 0, 1], "indeterminate": [3, 0, 1], "rejected": [1, 4, 0]}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def verify(executable, bundle):
    matches = shutil.which(executable)
    require(matches, "Belenios executable unavailable")
    tool = str(Path(matches).resolve())
    with ZipFile(bundle) as z, tempfile.TemporaryDirectory() as scratch:
        root = Path(scratch)
        env = {"PATH": os.defpath, "HOME": scratch, "TMPDIR": scratch, "LC_ALL": "C"}
        version = subprocess.check_output([tool, "--version"], cwd=root, env=env, timeout=30)
        require(version.split()[:1] == [b"3.3.0"], "requires Belenios 3.3.0")
        allowed = {"report.json"} | {f"{case}/{stage}/election.bel" for case in EXPECTED
                                      for stage in ("setup", "final")}
        require(len(z.infolist()) == len(allowed) and set(z.namelist()) == allowed
                and all(item.file_size <= 1024 * 1024 for item in z.infolist()), "unexpected bundle contents")
        report = json.loads(z.read("report.json"))
        rows = report["cases"]
        require(report["schema"] == "volparossa.citizen.belenios-demo.v1" and
                [row["outcome"] for row in rows] == list(EXPECTED), "unexpected case manifest")
        for row in rows:
            case = row["outcome"]
            counts = EXPECTED[case]
            for stage in ("setup", "final"):
                path = root / case / stage / "election.bel"
                path.parent.mkdir(parents=True)
                path.write_bytes(z.read(f"{case}/{stage}/election.bel"))
            setup, final = root / case / "setup", root / case / "final"
            archived = hashlib.sha256((final / "election.bel").read_bytes()).hexdigest()
            require(archived == row["public_archive_sha256"], f"{case}: archive digest differs")

            def run(*args):
                return subprocess.check_output([tool, "election", *args], cwd=final, env=env, timeout=30)

            run("verify-diff", "--dir1", setup, "--dir2", final)
            checksums = json.loads(run("compute-checksums"))
            require(checksums.get("final") and checksums.get("encrypted_tally")
                    and checksums["num_voters"] == 5, f"{case}: missing closed election or credentials")
            with tarfile.open(setup / "election.bel", "r:") as archive:
                election = archive.getmember(checksums["election"] + ".data.json")
                require(election.isfile(), "unexpected election definition")
                definition = json.load(archive.extractfile(election))
            require(definition["name"] == "sim-library-hours" and definition["group"] == "Ed25519"
                    and definition["questions"] == [{"question": "Extend the fictional library's Saturday hours?",
                        "answers": ["Yes", "No", "Abstain"], "min": 1, "max": 1}],
                    f"{case}: unexpected referendum question or answer order")
            require([row[k] for k in ("electorate", "registered_accounts", "support", "support_required",
                                      "decision_required", "not_voted")] == [6, 5, 2, 2, 4, 6 - sum(counts)],
                    f"{case}: Citizen fixture rules differ")
            require(json.loads(run("compute-result"))["result"] == [counts]
                    and [row["yes"], row["no"], row["abstain"]] == counts
                    and len(json.loads(run("compute-ballot-summary"))) == row["verified_ballots"] == sum(counts),
                    f"{case}: tally or ballot count differs")
            print(f"{case}: {sum(counts)} verified ballots, yes/no/abstain {counts}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle", type=Path)
    parser.add_argument("--tool", default="belenios-tool")
    args = parser.parse_args()
    verify(args.tool, args.bundle)
