# SPDX-License-Identifier: GPL-3.0-only
"""Offline library-hours exercise with the external Belenios 3.3.0 command-line tool."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from zipfile import ZipFile, ZIP_DEFLATED

from citizen import Choice, Electorate, Procedure, ProcedureError, Proposal, Registration, synthetic_identity

START = "2026-01-01T00:00:00Z"
SUPPORT_END = "2026-02-01T00:00:00Z"
CLOSE = "2026-03-01T00:00:00Z"
QUESTION = {"question": "Extend the fictional library's Saturday hours?",
            "answers": ["Yes", "No", "Abstain"], "min": 1, "max": 1}
CASES = {
    "adopted": [Choice.YES] * 4 + [Choice.ABSTAIN],
    "indeterminate": [Choice.YES] * 3 + [Choice.ABSTAIN],
    "rejected": [Choice.NO] * 4 + [Choice.YES],
}


def check(condition, message):
    if not condition:
        raise ValueError(message)


class Tool:
    def __init__(self, executable):
        path = shutil.which(executable)
        check(path is not None, "Belenios 3.3.0 executable unavailable")
        self.path = str(Path(path).resolve())

    def __call__(self, directory, *args, data=b"", rejects=False):
        result = subprocess.run([self.path, *args], cwd=directory, input=data, capture_output=True,
                                env={"PATH": os.defpath, "HOME": str(directory), "TMPDIR": str(directory),
                                     "BELENIOS_USE_URANDOM": "1", "LC_ALL": "C"},
                                timeout=30, check=False)
        if rejects:
            check(result.returncode > 0 and b"check_result failed" in result.stderr, "altered result was not rejected by the verifier")
        else:
            check(result.returncode == 0, "Belenios operation failed: " + " ".join(args[:2]))
        return result.stdout


def setup(tool, work, people):
    uid = tool(work, "setup", "generate-token").decode("ascii").strip()
    check(uid.isalnum() and 10 <= len(uid) <= 64, "invalid Belenios election identifier")
    options = ("--uuid", uid, "--group", "Ed25519")
    (work / "voters").write_text("\n".join(people) + "\n")
    (work / "template").write_text(json.dumps({"name": "sim-library-hours", "description":
        "Fictional Citizen referendum, revision 1.", "questions": [QUESTION]}))
    tool(work, "setup", "generate-credentials", *options, "--file", "voters")
    [private] = work.glob("*.privcreds")
    credentials = json.loads(private.read_bytes())
    check(set(credentials) == set(people), "credential roster differs from the registered electorate")
    [public] = work.glob("*.pubcreds")
    public.rename(work / "public_creds.json")
    tool(work, "setup", "generate-trustee-key", "--group", "Ed25519")
    [public_key] = work.glob("*.pubkey")
    public_key.rename(work / "public_keys.jsons")
    tool(work, "setup", "make-trustees")
    tool(work, "setup", "make-election", *options, "--template", "template")
    tool(work, "archive", "init")
    return work / (uid + ".bel"), credentials


def cast(tool, work, credential, choice):
    # Private arguments use files inside the disposable private directory, never argv.
    (work / "credential").write_text(credential + "\n")
    (work / "choice").write_text(json.dumps([[int(choice is option) for option in Choice]]))
    ballot = tool(work, "election", "generate-ballot", "--privcred", "credential", "--choice", "choice")
    tool(work, "archive", "add-event", "--type", "Ballot", data=ballot)


def scenario(tool, public, name, choices):
    people = tuple(synthetic_identity(i) for i in range(1, 7))
    registered = people[:5]
    procedure = Procedure("sim-" + name, Proposal("sim-library-hours", 1, "sim-town"),
                          Electorate("sim-town-roll", "sim-town", START, people), Registration(registered),
                          starts_at=START, support_until=SUPPORT_END, closes_at=CLOSE)
    procedure.support(people[0], at=START)
    check(procedure.state == "collecting_support", "one supporter opened a six-person referendum")
    procedure.support(people[1], at=START)
    check(procedure.state == "referendum", "required support did not open the referendum")
    initial, final = public / "setup", public / "final"
    initial.mkdir(parents=True)
    final.mkdir()
    changed = public / "altered"
    changed.mkdir()
    with tempfile.TemporaryDirectory() as private:
        work = Path(private)
        archive, credentials = setup(tool, work, registered)
        shutil.copyfile(archive, initial / "election.bel")
        for person, choice in zip(registered, choices):
            procedure.vote(person, choice, at=SUPPORT_END)
            cast(tool, work, credentials[person], choice)
        try:
            procedure.vote(registered[0], Choice.ABSTAIN, at=SUPPORT_END)
        except ProcedureError as exc:
            check(str(exc) == "DUPLICATE_VOTE", "unexpected duplicate decision")
        else:
            raise ValueError("Citizen accepted a repeat vote")
        procedure.close(at=CLOSE)
        report = procedure.report()
        tool(work, "archive", "add-event", "--type", "EndBallots")
        encrypted = tool(work, "election", "compute-encrypted-tally")
        tool(work, "archive", "add-event", "--type", "EncryptedTally", data=encrypted)
        [key] = work.glob("*.privkey")
        decryption = tool(work, "election", "decrypt", "--privkey", key.name, "--trustee-id", "1")
        tool(work, "archive", "add-event", "--type", "PartialDecryption", data=decryption)
        shutil.copyfile(archive, changed / archive.name)
        result = tool(work, "election", "compute-result")
        tool(work, "archive", "add-event", "--type", "Result", data=result)
        shutil.copyfile(archive, final / "election.bel")
        # The altered archive uses Belenios' own event writer, with valid archive framing.
        wrong = json.loads(result)
        wrong["result"][0][0] += 1
        tool(changed, "archive", "add-event", "--type", "Result", data=json.dumps(wrong, separators=(",", ":")).encode())
        del credentials
    # The private workspace is gone before checking either proposed result.
    tool(changed, "election", "verify", rejects=True)
    shutil.rmtree(changed)
    tool(final, "election", "verify-diff", "--dir1", str(initial), "--dir2", str(final))
    checksums = json.loads(tool(final, "election", "compute-checksums"))
    initial_checksums = json.loads(tool(initial, "election", "compute-checksums"))
    check(all(checksums[k] == v for k, v in initial_checksums.items())
          and checksums.get("final") and checksums.get("encrypted_tally"),
          "closed archive does not preserve the public setup")
    check(checksums["num_voters"] == len(registered), "unexpected public credential count")
    summary = json.loads(tool(final, "election", "compute-ballot-summary"))
    counts = json.loads(tool(final, "election", "compute-result"))["result"]
    check(len(summary) == len(choices) and counts == [[report["yes"], report["no"], report["abstain"]]]
          and report["outcome"] == name, "verified aggregate disagrees with the Citizen procedure")
    return {k: report[k] for k in ("procedure_id", "proposal_id", "proposal_revision", "electorate",
            "registered_accounts", "support", "support_required", "decision_required", "yes", "no",
            "abstain", "not_voted", "outcome")} | {
        "verified_ballots": len(summary), "public_setup_preserved": True, "altered_result_rejected": True,
        "public_archive_sha256": hashlib.sha256((final / "election.bel").read_bytes()).hexdigest()}


def bundle(public, target):
    # Publish only the complete public bundle, leaving any existing destination untouched.
    with tempfile.NamedTemporaryFile(dir=target.parent) as output:
        with ZipFile(output, "w", compression=ZIP_DEFLATED) as z:
            for path in sorted(public.glob("*/*/*.bel")):
                z.write(path, path.relative_to(public))
            z.write(public / "report.json", "report.json")
        output.flush()
        os.fsync(output.fileno())
        os.link(output.name, target)


def run(executable, public_bundle=None):
    tool = Tool(executable)
    with tempfile.TemporaryDirectory() as scratch:
        public = Path(scratch)
        version = tool(public, "--version").decode("ascii").strip()
        check(version.partition(" ")[0] == "3.3.0", "requires Belenios 3.3.0")
        cases = [scenario(tool, public / name, name, choices) for name, choices in CASES.items()]
        report = {"schema": "volparossa.citizen.belenios-demo.v1", "mode": "synthetic-offline-exercise",
                  "tool_version": version, "cases": cases, "real_identity_verified": False,
                  "independent_trustee_administration": False, "legal_authority": False}
        (public / "report.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
        if public_bundle is not None:
            bundle(public, Path(public_bundle))
        return report
