# SPDX-License-Identifier: GPL-3.0-only
from dataclasses import FrozenInstanceError
import json
from pathlib import Path
import subprocess
import sys
import unittest

from citizen import (Choice, Electorate, Outcome, Procedure, ProcedureError, Proposal,
                     Registration, anniversary, demo, synthetic_identity, timestamp, utc)


START = "2026-01-01T00:00:00Z"
SUPPORT_END = "2026-02-01T00:00:00Z"
CLOSE = "2026-03-01T00:00:00Z"
REPEAT = "2029-03-01T00:00:00Z"


def make(size=101, registered=None):
    people = tuple(synthetic_identity(number) for number in range(1, size + 1))
    registry = Registration(people if registered is None else registered)
    electorate = Electorate("sim-snapshot-one", "sim-town", START, people)
    procedure = Procedure("sim-procedure-one", Proposal("sim-library", 1, "sim-town"), electorate,
                          registry, starts_at=START, support_until=SUPPORT_END, closes_at=CLOSE)
    return procedure, registry, people


def open_ballot(procedure, people):
    for person in people[:procedure.report()["support_required"]]:
        procedure.support(person, at=START)


def tally(size, yes, no, abstain=0):
    procedure, _, people = make(size)
    open_ballot(procedure, people)
    for choice, begin, end in ((Choice.YES, 0, yes), (Choice.NO, yes, yes + no),
                              (Choice.ABSTAIN, yes + no, yes + no + abstain)):
        for person in people[begin:end]:
            procedure.vote(person, choice, at=SUPPORT_END)
    procedure.close(at=CLOSE)
    return procedure


class CitizenSimulation(unittest.TestCase):
    def error(self, code, action):
        with self.assertRaisesRegex(ProcedureError, f"^{code}$"):
            action()

    def test_one_third_support_exact_integer_boundaries(self):
        for size in (1, 2, 3, 4, 6, 100, 101):
            with self.subTest(size=size):
                procedure, _, people = make(size)
                required = (size + 2) // 3
                for person in people[:required - 1]:
                    procedure.support(person, at=START)
                self.assertEqual(procedure.state, "collecting_support")
                procedure.support(people[required - 1], at=START)
                self.assertEqual(procedure.state, "referendum")
                self.assertEqual(procedure.report()["yes"], 0)

    def test_two_thirds_uses_entire_population(self):
        for size in (1, 2, 3, 4, 6, 100, 101):
            required = (2 * size + 2) // 3
            with self.subTest(size=size):
                self.assertEqual(tally(size, required, 0).outcome, Outcome.ADOPTED)
                self.assertEqual(tally(size, 0, required).outcome, Outcome.REJECTED)
                self.assertEqual(tally(size, required - 1, 0).outcome, Outcome.INDETERMINATE)
                self.assertEqual(tally(size, 0, required - 1).outcome, Outcome.INDETERMINATE)

    def test_turnout_majority_is_not_approval_and_reverse_is_not_rejection(self):
        self.assertEqual(tally(101, 67, 34).outcome, Outcome.INDETERMINATE)
        self.assertEqual(tally(101, 34, 67).outcome, Outcome.INDETERMINATE)
        self.assertEqual(tally(101, 1, 0).outcome, Outcome.INDETERMINATE)

    def test_abstention_and_absence_do_not_shrink_denominator(self):
        for abstain in (0, 34):
            report = tally(101, 67, 0, abstain).report()
            self.assertEqual(report["outcome"], "indeterminate")
            self.assertEqual(report["electorate"], 101)
            self.assertEqual(report["not_voted"], 34 - abstain)

    def test_registration_separate_from_eligibility_and_mutable_accounts(self):
        procedure, registry, people = make(101, registered=[])
        self.assertEqual(procedure.report()["electorate"], 101)
        self.error("NOT_REGISTERED", lambda: procedure.support(people[0], at=START))
        registry.register(people[0])
        registry.register(synthetic_identity(102))  # child/other ineligible registered person
        procedure.support(people[0], at=START)
        self.error("NOT_ELIGIBLE", lambda: procedure.support(synthetic_identity(102), at=START))
        self.assertEqual(procedure.report()["registered_accounts"], 2)
        self.assertEqual(procedure.report()["support_required"], 34)

    def test_duplicate_registration_and_input_rosters_rejected(self):
        person = synthetic_identity(1)
        registry = Registration([person])
        self.error("DUPLICATE_REGISTRATION", lambda: registry.register(person))
        self.error("DUPLICATE_IDENTITY", lambda: Registration([person, person]))
        self.error("DUPLICATE_IDENTITY", lambda: Electorate("sim-one", "sim-town", START, [person, person]))

    def test_electorate_is_copied_and_frozen_not_an_account_set(self):
        roster = [synthetic_identity(1), synthetic_identity(2)]
        snapshot = Electorate("sim-one", "sim-town", START, roster)
        roster.append(synthetic_identity(3))
        self.assertEqual(len(snapshot.all_eligible), 2)
        with self.assertRaises(FrozenInstanceError):
            snapshot.all_eligible = ()
        procedure, _, _ = make()
        with self.assertRaises(AttributeError):
            procedure.electorate = snapshot

    def test_empty_oversized_invalid_and_duplicate_population_refused(self):
        for roster, code in (([], "EMPTY_ELECTORATE"), (["real-name"], "IDENTITY_INVALID"),
                             ([synthetic_identity(1)] * 10001, "ROSTER_INVALID")):
            self.error(code, lambda: Electorate("sim-one", "sim-town", START, roster))

    def test_duplicate_support_and_votes_have_no_effect(self):
        procedure, _, people = make()
        procedure.support(people[0], at=START)
        before = procedure.report()
        self.error("DUPLICATE_SUPPORT", lambda: procedure.support(people[0], at=START))
        self.assertEqual(before, procedure.report())
        for person in people[1:34]:
            procedure.support(person, at=START)
        procedure.vote(people[0], Choice.NO, at=SUPPORT_END)  # supporting != voting yes
        before = procedure.report()
        self.error("DUPLICATE_VOTE", lambda: procedure.vote(people[0], Choice.YES, at=SUPPORT_END))
        self.assertEqual(before, procedure.report())

    def test_noneligible_vote_and_unknown_choice_rejected(self):
        procedure, registry, people = make()
        registry.register(synthetic_identity(102))
        open_ballot(procedure, people)
        self.error("NOT_ELIGIBLE", lambda: procedure.vote(synthetic_identity(102), Choice.YES, at=START))
        self.error("CHOICE_INVALID", lambda: procedure.vote(people[0], "yes", at=START))
        self.assertEqual(procedure.report()["not_voted"], 101)

    def test_wrong_jurisdiction_future_snapshot_and_bad_schedule_rejected(self):
        procedure, registry, _ = make()
        for proposal, start, end, close, code in (
            (Proposal("sim-other", 1, "sim-other"), START, SUPPORT_END, CLOSE, "JURISDICTION_MISMATCH"),
            (Proposal("sim-other", 1, "sim-town"), "2025-01-01T00:00:00Z", SUPPORT_END, CLOSE, "SCHEDULE_INVALID"),
            (Proposal("sim-other", 1, "sim-town"), START, CLOSE, CLOSE, "SCHEDULE_INVALID")):
            self.error(code, lambda: Procedure("sim-bad", proposal, procedure.electorate, registry,
                starts_at=start, support_until=end, closes_at=close))

    def test_support_and_ballot_windows_and_event_time_are_checked(self):
        procedure, _, people = make()
        self.error("REFERENDUM_NOT_OPEN", lambda: procedure.vote(people[0], Choice.YES, at=START))
        self.error("SUPPORT_WINDOW_CLOSED", lambda: procedure.support(people[0], at=SUPPORT_END))
        open_ballot(procedure, people)
        self.error("SUPPORT_CLOSED", lambda: procedure.support(people[34], at=START))
        procedure.vote(people[0], Choice.YES, at=SUPPORT_END)
        self.error("TIME_REGRESSION", lambda: procedure.vote(people[1], Choice.YES, at=START))
        self.error("BALLOT_WINDOW_CLOSED", lambda: procedure.vote(people[1], Choice.YES, at=CLOSE))
        self.error("BALLOT_STILL_OPEN", lambda: procedure.close(at=SUPPORT_END))
        procedure.close(at=CLOSE)
        self.error("REFERENDUM_NOT_OPEN", lambda: procedure.vote(people[1], Choice.YES, at=CLOSE))
        self.error("REFERENDUM_NOT_OPEN", lambda: procedure.close(at=CLOSE))

    def test_no_outcome_without_support_and_explicit_close(self):
        procedure, _, people = make()
        self.error("REFERENDUM_NOT_OPEN", lambda: procedure.close(at=CLOSE))
        open_ballot(procedure, people)
        self.assertIsNone(procedure.outcome)
        self.assertFalse(procedure.can_resubmit(at=REPEAT))
        self.assertEqual(procedure.state, "referendum")

    def test_repeat_after_three_calendar_years_requires_explicit_action(self):
        procedure = tally(101, 67, 34)
        before = procedure.report()
        self.assertFalse(procedure.can_resubmit(at="2029-02-28T23:59:59Z"))
        self.assertTrue(procedure.can_resubmit(at=REPEAT))
        self.assertEqual(procedure.report(), before)
        snapshot = Electorate("sim-two", "sim-town", REPEAT, [synthetic_identity(1)])
        successor = procedure.resubmit("sim-two", snapshot, at=REPEAT,
            support_until="2029-04-01T00:00:00Z", closes_at="2029-05-01T00:00:00Z")
        self.assertEqual(successor.state, "collecting_support")
        self.assertEqual(successor.report()["support"], 0)
        self.assertEqual(successor.report()["yes"], 0)
        self.assertEqual(successor.report()["electorate"], 1)
        self.assertEqual(procedure.report()["electorate"], 101)
        self.assertFalse(procedure.can_resubmit(at=REPEAT))
        self.error("RESUBMISSION_NOT_ALLOWED", lambda: procedure.resubmit("sim-three", snapshot,
            at=REPEAT, support_until="2029-04-01T00:00:00Z", closes_at="2029-05-01T00:00:00Z"))

    def test_repeat_before_boundary_adopted_and_rejected_refused(self):
        for procedure, at in ((tally(101, 67, 34), "2029-02-28T23:59:59Z"),
                              (tally(101, 68, 33), REPEAT), (tally(101, 33, 68), REPEAT)):
            snapshot = Electorate("sim-two", "sim-town", at, [synthetic_identity(1)])
            self.error("RESUBMISSION_NOT_ALLOWED", lambda: procedure.resubmit("sim-two", snapshot,
                at=at, support_until="2029-04-01T00:00:00Z", closes_at="2029-05-01T00:00:00Z"))

    def test_invalid_repeat_does_not_consume_permission_or_reuse_snapshot(self):
        procedure = tally(101, 67, 34)
        self.error("NEW_PROCEDURE_REQUIRED", lambda: procedure.resubmit("sim-two", procedure.electorate,
            at=REPEAT, support_until="2029-04-01T00:00:00Z", closes_at="2029-05-01T00:00:00Z"))
        old_reference = Electorate("sim-two", "sim-town", START, [synthetic_identity(1)])
        self.error("NEW_SNAPSHOT_REQUIRED", lambda: procedure.resubmit("sim-two", old_reference,
            at=REPEAT, support_until="2029-04-01T00:00:00Z", closes_at="2029-05-01T00:00:00Z"))
        self.assertTrue(procedure.can_resubmit(at=REPEAT))

    def test_calendar_years_not_days_and_february_29_assumption(self):
        self.assertEqual(timestamp(anniversary(utc("2028-02-29T12:13:14Z"))), "2031-02-28T12:13:14Z")
        self.assertEqual(timestamp(anniversary(utc("2027-03-01T00:00:00Z"))), "2030-03-01T00:00:00Z")
        self.assertEqual((anniversary(utc("2027-03-01T00:00:00Z")) - utc("2027-03-01T00:00:00Z")).days, 1096)
        self.error("CALENDAR_RANGE", lambda: anniversary(utc("9997-01-01T00:00:00Z")))

    def test_actual_leap_day_procedure_repeat_boundary(self):
        person = synthetic_identity(1)
        procedure = Procedure("sim-leap", Proposal("sim-library", 1, "sim-town"),
            Electorate("sim-before-leap", "sim-town", "2028-01-01T00:00:00Z", [person]),
            Registration([person]), starts_at="2028-01-01T00:00:00Z",
            support_until="2028-02-01T00:00:00Z", closes_at="2028-02-29T12:13:14Z")
        procedure.support(person, at="2028-01-02T00:00:00Z")
        procedure.vote(person, Choice.ABSTAIN, at="2028-02-01T00:00:00Z")
        procedure.close(at="2028-03-01T00:00:00Z")  # Delayed close does not reset anniversary.
        before = procedure.report()
        self.assertEqual(before["resubmission_not_before"], "2031-02-28T12:13:14Z")
        self.assertFalse(procedure.can_resubmit(at="2031-02-28T12:13:13Z"))
        self.assertTrue(procedure.can_resubmit(at="2031-02-28T12:13:14Z"))
        self.assertEqual(procedure.report(), before)
        repeat = procedure.resubmit("sim-leap-repeat",
            Electorate("sim-after-leap", "sim-town", "2031-02-28T12:13:14Z", [person]),
            at="2031-02-28T12:13:14Z", support_until="2031-03-01T00:00:00Z",
            closes_at="2031-04-01T00:00:00Z")
        self.assertEqual(repeat.state, "collecting_support")
        self.assertEqual(repeat.report()["abstain"], 0)

    def test_time_parser_does_not_accept_local_or_ambiguous_times(self):
        for value in ("2026-01-01", "2026-01-01T00:00:00+00:00", "2026-02-29T00:00:00Z", "2026-01-01T00:00:60Z", None):
            self.error("TIME_INVALID", lambda: utc(value))

    def test_no_claims_of_secrecy_identity_transport_or_legal_force(self):
        for result in demo()["cases"]:
            for field in ("real_identity_verified", "secret_ballot", "core_transport", "legal_authority"):
                self.assertIs(result[field], False)
            self.assertNotIn("votes", result)
        self.assertEqual(demo(), demo())

    def test_actual_demo_cli_deterministic_and_unknown_command_rejected(self):
        path = Path(__file__).resolve().parents[1] / "citizen.py"
        runs = [subprocess.run([sys.executable, "-B", str(path), "demo"], capture_output=True, timeout=5)
                for _ in range(2)]
        self.assertTrue(all(run.returncode == 0 and run.stderr == b"" for run in runs))
        self.assertEqual(runs[0].stdout, runs[1].stdout)
        data = json.loads(runs[0].stdout)
        self.assertEqual([case["outcome"] for case in data["cases"]], ["adopted", "rejected", "indeterminate"])
        self.assertIsNone(data["before_explicit_request"]["successor"])
        self.assertEqual(data["explicit_successor"]["state"], "collecting_support")
        invalid = subprocess.run([sys.executable, "-B", str(path), "enroll-real-voters"], capture_output=True, timeout=5)
        self.assertNotEqual(invalid.returncode, 0)


if __name__ == "__main__":
    unittest.main()
