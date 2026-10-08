# VOLPAROSSA Citizen

Citizen is an application for decentralized proposals, deliberation and referenda,
intended to work alongside existing democratic institutions. This first executable
component simulates the agreed support and voting rules using fictional identities.
It is not a live election service, an identity-verification system or legal authority.

## Run the simulation

Python 3.10 or newer is sufficient; no dependency installation is needed.

```sh
python3 -B citizen.py demo
python3 -B -m unittest discover -s tests -v
```

The deterministic demo emits JSON for adoption, rejection, an indeterminate result
and an explicitly requested repeat procedure. It uses 101 eligible fictional
residents and 102 registered accounts, including an ineligible child record.
It opens no sockets, reads no identity documents and writes no application data.
Ballots exist in plain text in process memory: this is deliberately not secret voting.

## Implemented rules

An immutable, declared-complete synthetic electorate fixes `N` before support
collection. Eligible people without an account still count in `N`; registering an
account does not change eligibility. Participation in this simulation requires an
account and membership in the frozen electorate. Registering a child gives neither
the child nor a parent any extra voting entitlement.

| Decision | Exact rule based on all eligible people |
| --- | --- |
| Start referendum | `3 * distinct_supporters >= N` |
| Adopt proposal | `3 * yes_votes >= 2 * N` |
| Reject proposal | `3 * no_votes >= 2 * N` |
| Indeterminate result | Neither decision threshold is reached |

For 101 eligible people, 34 supporters start the referendum and 68 yes or 68 no
votes determine its outcome. Both 67 yes with 34 no and 34 yes with 67 no are
indeterminate. Abstentions and nonparticipation never reduce the denominator.
Supporting a referendum does not cast a yes vote.

The simulator rejects duplicate identities in a roster, repeated registrations,
duplicate support or votes, ineligible participants, a mismatched jurisdiction,
backdated events and out-of-window activity. Integer arithmetic avoids floating
point threshold rounding. Each electorate and registration is bounded to 10,000
synthetic identities; this is a test limit, not the intended population ceiling.
The model has no public operation for replacing an active electorate or proposal.

An indeterminate procedure becomes eligible for an explicit repeat request after
three calendar years. Checking eligibility does not open a ballot or schedule work.
The old electorate and result remain unchanged; a new procedure starts with a
newly fixed electorate and empty support and ballots.

## Explicit procedural assumptions

These details make the simulation deterministic; they are not additional confirmed
governance rules:

- The three-year interval starts at the scheduled ballot closing time, in UTC.
  February 29 maps to February 28 three years later, preserving the time of day.
  Three calendar years are not implemented as 1,095 days.
- Support begins at the declared start and ends before its deadline. Reaching one
  third opens voting immediately. Ballots are accepted before their closing time;
  the tally requires an explicit close operation at or after that time.
- A repeat retains the proposal identifier and version, requires a newly declared
  electorate snapshot and collects one-third support again. Only one successor can
  be requested from a closed procedure through this workflow. Approved/rejected
  reconsideration and materially revised proposals have no repeat policy here.
- Re-registration of the same synthetic identity is refused. Document renewal,
  multiple nationalities, identity recovery, revocation, appeals and revoting need
  separate policies; another synthetic identifier is not proof of another human.
  The caller supplies eligibility and jurisdiction; the simulator does not decide
  citizenship, residence, voting age or lawful authority.

## Implementation status

- [x] Runnable deterministic support, ballot, tally and explicit repeat workflow.
- [x] Frozen all-eligible denominator separate from accounts and turnout.
- [x] Targeted tests for thresholds, duplicate inputs, time boundaries, registration,
  snapshot immutability, calendar anniversaries and actual demo execution.
- [ ] Inclusive real-world registration and independently verified register coverage.
- [ ] Secret ballots, audited eligibility proofs and independent cryptographic tally verification.
- [ ] Proposal review using the values framework, contestable jurisdiction and appeals.
- [ ] Core transport, encrypted storage, distributed execution and recovery.
- [ ] Native/web interfaces and an independently authorized real-world pilot.

Python objects and caller-supplied timestamps are trusted simulation inputs, not a
hostile-client security boundary. Recognizing `sim-person-00001` is syntax validation,
not authentication or worldwide duplicate detection. No account API, passport parser,
cryptographic voting implementation, peer protocol or installation service is included.
The core should supply reusable transport, storage and compute; Citizen retains its
application-specific participation rules.

## Open source building blocks

These candidates are research inputs, not dependencies or adopted protocols:

- [Decidim](https://docs.decidim.org/en/develop/features/general-description.html)
  separates participation spaces and components such as proposals and meetings.
  It is a candidate for deliberation workflows, not a decentralized transport layer.
- [AnonCreds Rust](https://github.com/anoncreds/anoncreds-rs) implements anonymous
  credential handling. It is a candidate for a later credential adapter; issuance
  trust and complete electorate coverage remain separate problems.
- [Belenios](https://www.belenios.org/faq.html) offers verifiable voting with separate
  authorities, but documents coercion and compromised-device limitations. A later
  synthetic-ballot integration must validate its actual proofs and reconcile its
  revoting rules with Citizen's chosen procedure.

Select and pin an audited upstream version before importing code, retain its license
and notices, and test its trust assumptions. This simulation invents no cryptography
and imports none of those implementations. Original source here uses GPL-3.0-only;
the repository's existing [license](LICENSE) is unchanged.
