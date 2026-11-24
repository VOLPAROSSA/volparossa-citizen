#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Deterministic, in-memory Citizen procedure simulation. No real identities."""
from bisect import bisect_left
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
import argparse
import json
import re


MAX_IDENTITIES = 10_000


class ProcedureError(ValueError):
    """Fixed diagnostic codes, never identity or ballot contents."""


def require(condition, code):
    if not condition:
        raise ProcedureError(code)


def synthetic_identity(number):
    require(type(number) is int and 1 <= number <= MAX_IDENTITIES, "IDENTITY_INVALID")
    return f"sim-person-{number:05d}"


def identity(value):
    require(type(value) is str and re.fullmatch(r"sim-person-[0-9]{5}", value) is not None,
            "IDENTITY_INVALID")
    require(1 <= int(value[-5:]) <= MAX_IDENTITIES, "IDENTITY_INVALID")
    return value


def label(value):
    require(type(value) is str and re.fullmatch(r"sim-[a-z0-9-]{1,60}", value) is not None,
            "LABEL_INVALID")
    return value


def utc(value):
    require(type(value) is str and re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z", value)
            is not None, "TIME_INVALID")
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        raise ProcedureError("TIME_INVALID") from None


def timestamp(value):
    return value.isoformat(timespec="seconds").replace("+00:00", "Z")


def anniversary(value):
    """Explicit simulation assumption: UTC; February 29 maps to February 28."""
    require(value.year <= 9996, "CALENDAR_RANGE")
    try:
        return value.replace(year=value.year + 3)
    except ValueError:
        return value.replace(year=value.year + 3, day=28)


def identities(values):
    require(type(values) in (tuple, list) and len(values) <= MAX_IDENTITIES, "ROSTER_INVALID")
    copied = tuple(identity(value) for value in values)
    require(len(set(copied)) == len(copied), "DUPLICATE_IDENTITY")
    return tuple(sorted(copied))


class Registration:
    """Synthetic platform accounts; neither an eligibility authority nor deduplication."""
    __slots__ = ("_registered",)

    def __init__(self, registered=()):
        self._registered = set(identities(registered))

    def register(self, person):
        identity(person)
        require(person not in self._registered, "DUPLICATE_REGISTRATION")
        require(len(self._registered) < MAX_IDENTITIES, "REGISTRATION_FULL")
        self._registered.add(person)

    def contains(self, person):
        return person in self._registered

    @property
    def count(self):
        return len(self._registered)


@dataclass(frozen=True)
class Electorate:
    """Declared complete synthetic eligible population, including non-account holders."""
    snapshot_id: str
    jurisdiction: str
    reference_at: str
    all_eligible: tuple

    def __post_init__(self):
        label(self.snapshot_id)
        label(self.jurisdiction)
        utc(self.reference_at)
        copied = identities(self.all_eligible)
        require(len(copied) > 0, "EMPTY_ELECTORATE")
        object.__setattr__(self, "all_eligible", copied)

    def contains(self, person):
        index = bisect_left(self.all_eligible, person)
        return index < len(self.all_eligible) and self.all_eligible[index] == person


@dataclass(frozen=True)
class Proposal:
    proposal_id: str
    revision: int
    jurisdiction: str

    def __post_init__(self):
        label(self.proposal_id)
        label(self.jurisdiction)
        require(type(self.revision) is int and 1 <= self.revision <= 1_000_000, "REVISION_INVALID")


class Choice(str, Enum):
    YES = "yes"
    NO = "no"
    ABSTAIN = "abstain"


class Outcome(str, Enum):
    ADOPTED = "adopted"
    REJECTED = "rejected"
    INDETERMINATE = "indeterminate"



def referendum_outcome(yes, no, eligible):
    if 3 * yes >= 2 * eligible:
        return Outcome.ADOPTED
    if 3 * no >= 2 * eligible:
        return Outcome.REJECTED
    return Outcome.INDETERMINATE


class Procedure:
    """Single-process reference workflow, not an authenticated election service."""
    __slots__ = ("_id", "_proposal", "_electorate", "_registration", "_start", "_support_end",
                 "_close", "_last", "_supporters", "_voters", "_counts", "_closed_participation",
                 "_opened", "_outcome", "_successor")

    def __init__(self, procedure_id, proposal, electorate, registration, *, starts_at,
                 support_until, closes_at):
        self._id = label(procedure_id)
        require(type(proposal) is Proposal and type(electorate) is Electorate
                and type(registration) is Registration, "PROCEDURE_INVALID")
        require(proposal.jurisdiction == electorate.jurisdiction, "JURISDICTION_MISMATCH")
        start, support_end, close = utc(starts_at), utc(support_until), utc(closes_at)
        require(utc(electorate.reference_at) <= start < support_end < close, "SCHEDULE_INVALID")
        anniversary(close)  # Refuse an unrepresentable repeat boundary at creation.
        self._proposal, self._electorate, self._registration = proposal, electorate, registration
        self._start, self._support_end, self._close, self._last = start, support_end, close, start
        self._supporters, self._voters = set(), set()
        self._counts = {choice: 0 for choice in Choice}
        self._closed_participation = None
        self._opened = self._outcome = self._successor = None

    @property
    def electorate(self):
        return self._electorate

    @property
    def outcome(self):
        return self._outcome

    @property
    def state(self):
        if self._outcome is not None:
            return "closed"
        return "referendum" if self._opened is not None else "collecting_support"

    def _event_time(self, at):
        now = utc(at)
        require(now >= self._last, "TIME_REGRESSION")
        return now

    def _participant(self, person):
        identity(person)
        require(self._electorate.contains(person), "NOT_ELIGIBLE")
        require(self._registration.contains(person), "NOT_REGISTERED")

    def support(self, person, *, at):
        now = self._event_time(at)
        require(self.state == "collecting_support", "SUPPORT_CLOSED")
        require(self._start <= now < self._support_end, "SUPPORT_WINDOW_CLOSED")
        self._participant(person)
        require(person not in self._supporters, "DUPLICATE_SUPPORT")
        self._supporters.add(person)
        if 3 * len(self._supporters) >= len(self._electorate.all_eligible):
            self._opened = now
        self._last = now

    def vote(self, person, choice, *, at):
        now = self._event_time(at)
        require(self.state == "referendum", "REFERENDUM_NOT_OPEN")
        require(self._opened <= now < self._close, "BALLOT_WINDOW_CLOSED")
        self._participant(person)
        require(type(choice) is Choice, "CHOICE_INVALID")
        require(person not in self._voters, "DUPLICATE_VOTE")
        self._voters.add(person)
        self._counts[choice] += 1
        self._last = now

    def close(self, *, at):
        now = self._event_time(at)
        require(self.state == "referendum", "REFERENDUM_NOT_OPEN")
        require(now >= self._close, "BALLOT_STILL_OPEN")
        size = len(self._electorate.all_eligible)
        yes, no = self._counts[Choice.YES], self._counts[Choice.NO]
        self._outcome = referendum_outcome(yes, no, size)
        self._closed_participation = (self._registration.count, len(self._supporters))
        self._supporters.clear()
        self._voters.clear()
        self._last = now
        return self._outcome

    def can_resubmit(self, *, at):
        now = utc(at)
        return (self._outcome is Outcome.INDETERMINATE and self._successor is None
                and now >= self._last and now >= anniversary(self._close))

    def resubmit(self, procedure_id, electorate, *, at, support_until, closes_at):
        require(self.can_resubmit(at=at), "RESUBMISSION_NOT_ALLOWED")
        label(procedure_id)
        require(procedure_id != self._id and type(electorate) is Electorate
                and electorate.snapshot_id != self._electorate.snapshot_id, "NEW_PROCEDURE_REQUIRED")
        require(utc(electorate.reference_at) > utc(self._electorate.reference_at), "NEW_SNAPSHOT_REQUIRED")
        # Explicit assumption: same proposal version, freshly fixed population,
        # fresh support. No old ballots/support or automatic scheduled action.
        successor = Procedure(procedure_id, self._proposal, electorate, self._registration,
                              starts_at=at, support_until=support_until, closes_at=closes_at)
        self._successor = procedure_id
        self._last = utc(at)
        return successor

    def report(self):
        accounts, support = (self._closed_participation if self._closed_participation is not None
                             else (self._registration.count, len(self._supporters)))
        counts = self._counts
        size = len(self._electorate.all_eligible)
        return {
            "schema": "volparossa.citizen.simulation.v1", "mode": "synthetic-simulation",
            "procedure_id": self._id, "proposal_id": self._proposal.proposal_id,
            "proposal_revision": self._proposal.revision,
            "jurisdiction": self._electorate.jurisdiction, "snapshot_id": self._electorate.snapshot_id,
            "electorate": size, "registered_accounts": accounts,
            "support_required": (size + 2) // 3, "decision_required": (2 * size + 2) // 3,
            "support": support, "yes": counts[Choice.YES], "no": counts[Choice.NO],
            "abstain": counts[Choice.ABSTAIN], "not_voted": size - sum(counts.values()),
            "state": self.state, "outcome": self._outcome.value if self._outcome else None,
            "closes_at": timestamp(self._close),
            "resubmission_not_before": timestamp(anniversary(self._close))
                if self._outcome is Outcome.INDETERMINATE else None,
            "successor": self._successor,
            "real_identity_verified": False, "secret_ballot": False,
            "core_transport": False, "legal_authority": False,
        }


def demo():
    people = tuple(synthetic_identity(index) for index in range(1, 102))
    registration = Registration(people + (synthetic_identity(102),))  # Registered child, ineligible.
    electorate = Electorate("sim-town-2026", "sim-town", "2026-10-01T00:00:00Z", people)
    proposal = Proposal("sim-library-hours", 1, "sim-town")
    cases = []
    for name, yes, no in (("adopted", 68, 33), ("rejected", 33, 68), ("indeterminate", 67, 34)):
        procedure = Procedure(f"sim-{name}", proposal, electorate, registration,
                              starts_at="2026-10-01T00:00:00Z", support_until="2026-11-01T00:00:00Z",
                              closes_at="2026-12-01T00:00:00Z")
        for person in people[:34]:
            procedure.support(person, at="2026-10-02T00:00:00Z")
        for person in people[:yes]:
            procedure.vote(person, Choice.YES, at="2026-11-02T00:00:00Z")
        for person in people[yes:yes + no]:
            procedure.vote(person, Choice.NO, at="2026-11-02T00:00:00Z")
        procedure.close(at="2026-12-01T00:00:00Z")
        cases.append(procedure.report())
    # Querying elapsed time does not create a successor or open a new ballot.
    allowed = procedure.can_resubmit(at="2029-12-01T00:00:00Z")
    before_explicit_request = procedure.report()
    successor = procedure.resubmit("sim-library-repeat",
        Electorate("sim-town-2029", "sim-town", "2029-12-01T00:00:00Z", people),
        at="2029-12-01T00:00:00Z", support_until="2030-01-01T00:00:00Z", closes_at="2030-02-01T00:00:00Z")
    return {"mode": "synthetic-simulation", "cases": cases,
            "elapsed_time_allows_request": allowed, "before_explicit_request": before_explicit_request,
            "explicit_successor": successor.report()}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("demo", help="run the in-memory fictional procedures")
    encrypted = commands.add_parser("belenios-demo", help="run the offline encrypted library-hours exercise")
    encrypted.add_argument("--tool", default="belenios-tool", help="installed Belenios 3.3.0 executable")
    encrypted.add_argument("--public-bundle", help="create a new ZIP with public setup and final archives")
    encrypted.add_argument("--setup-pin", help="write the three public setup digests to a new, separate file before voting")
    replay = commands.add_parser("belenios-replay", help="verify a public exercise against an independently retained setup")
    replay.add_argument("bundle", help="public referendum ZIP")
    cached = commands.add_parser("belenios-replay-cache", help="verify a signed referendum from existing local Core caches")
    cached.add_argument("manifest", help="signed Core publication manifest")
    cached.add_argument("--publisher-key", required=True, help="independently trusted Ed25519 publisher public key")
    cached.add_argument("--cache", action="append", required=True, help="existing local Core chunk store, repeat for multiple stores")
    cached.add_argument("--core", default="volparossa", help="installed VOLPAROSSA CLI")
    for reader in (replay, cached):
        reader.add_argument("--setup-pin", required=True, help="separately trusted setup digest file")
        reader.add_argument("--tool", default="belenios-tool", help="installed Belenios 3.3.0 executable")
    ballot = commands.add_parser("belenios-ballot", help="prepare and verify a private choice for an offline fictional referendum")
    ballot.add_argument("setup", help="public initial Belenios archive")
    ballot.add_argument("--setup-sha256", required=True, help="independently retained initial archive digest")
    ballot.add_argument("--output", required=True, help="new file for the encrypted ballot")
    ballot.add_argument("--tool", default="belenios-tool", help="installed Belenios 3.3.0 executable")
    single = commands.add_parser("belenios-tally", help="verify a closed Yes/No/Abstain referendum")
    single.add_argument("setup", help="public initial Belenios archive")
    single.add_argument("final", help="public closed Belenios archive")
    single.add_argument("--setup-sha256", required=True, help="independently retained initial archive digest")
    single.add_argument("--ballot-sha256", help="look for this voter’s tracker in the verified final count")
    single.add_argument("--eligible", type=int, required=True, help="independently established full eligible population")
    single.add_argument("--tool", default="belenios-tool", help="installed Belenios 3.3.0 executable")
    args = parser.parse_args()
    if args.command == "demo":
        result = demo()
    else:
        import subprocess
        import tarfile
        import zipfile
        try:
            if args.command == "belenios-replay":
                from integrations.belenios.replay import verify
                verify(args.tool, args.bundle, args.setup_pin)
                parser.exit(0)
            if args.command == "belenios-replay-cache":
                from integrations.belenios.replay import verify_cached
                verify_cached(args.core, args.tool, args.manifest, args.publisher_key, args.cache, args.setup_pin)
                parser.exit(0)
            if args.command == "belenios-ballot":
                from integrations.belenios.ballot import prepare_ballot
                result = prepare_ballot(args.tool, args.setup, args.setup_sha256, args.output)
            elif args.command == "belenios-tally":
                from integrations.belenios.tally import tally
                result = tally(args.tool, args.setup, args.final, args.setup_sha256, args.eligible, args.ballot_sha256)
            else:
                from belenios_demo import run
                result = run(args.tool, args.public_bundle, args.setup_pin)
        except (OSError, ValueError, KeyError, TypeError, zipfile.BadZipFile, tarfile.TarError, subprocess.SubprocessError) as error:
            parser.exit(1, f"{error}\n")
    print(json.dumps(result, indent=2, sort_keys=True))
