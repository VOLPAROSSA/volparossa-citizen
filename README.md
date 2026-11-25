![VOLPAROSSA Citizen — an open pop-up book with a town and people gathering around a table](docs/assets/banner-volparossa-citizen.png)

# VOLPAROSSA Citizen

**Make a public proposal's rules as inspectable as its result.**

Who is eligible, how much support starts a vote, and what does abstaining mean?
VOLPAROSSA Citizen is developing proposals, deliberation and referenda alongside
existing democratic institutions, with explicit rules that people can examine
and challenge. The intended [VOLPAROSSA core](https://github.com/VOLPAROSSA/volparossa)
integration supplies shared transport, private storage and compute; Citizen keeps
the procedure and eligibility rules visible in the application.

The executable starting point uses **fictional identities** to explore support,
voting and repeat procedures. It is not a recognized election, a real-person
identity check or legal authority. Help examine edge cases and the unresolved
registration and secret-ballot requirements before a real-world pilot.

[Follow the fictional library proposal in The Saturday Edition](https://volparossa.org/volparossa-citizen/).

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
Each vote updates the aggregate counts for yes, no and abstain. A separate set of
participants prevents duplicate votes. At closure, the simulator keeps the counts
and drops its supporter and voter lists. The caller can still observe choices as
they are cast.

## Verify an encrypted fictional referendum

An optional command runs the original Belenios 3.3.0 executable on three fictional
library-hours referenda. Each has six eligible residents, five registered accounts
and two supporters. Four yes votes adopt, four no votes reject, and three yes with
one abstention leave the proposal indeterminate. Belenios verifies the encrypted
ballots, the trustee's decryption and the published aggregate. Citizen applies
the thresholds against all six residents.

On Linux x86-64, Python and `dpkg-deb` can prepare the pinned Debian executable
and libraries in a **new** directory. Only the preparation step downloads files.
The other commands can run with the network disconnected.

```sh
python3 -B integrations/belenios/prepare.py ./belenios-runtime
python3 -B citizen.py belenios-demo --tool ./belenios-runtime/belenios-tool --public-bundle public-referenda.zip
python3 -B integrations/belenios/replay.py public-referenda.zip --tool ./belenios-runtime/belenios-tool
```

To identify the same three elections later, add `--setup-pin public-setup.json`
when running `belenios-demo`. Citizen writes the SHA-256 digest of each public
setup archive before casting the first ballot. Retain the file through a trusted
channel. Even a valid second run of the same exercise has different credentials
and trustee keys. A reader checks the intended elections with the following command.

```sh
python3 -B citizen.py belenios-replay public-referenda.zip --setup-pin public-setup.json --tool ./belenios-runtime/belenios-tool
```

A fictional voter on Linux can prepare an encrypted ballot on their own machine.
Use the initial archive and the digest obtained independently before the vote.
Read the question shown in the terminal, then enter the choice and the voter's
private Belenios credential at the hidden prompts.

```sh
python3 -B citizen.py belenios-ballot initial.bel --setup-sha256 "$TRUSTED_SETUP_SHA256" \
  --output encrypted-ballot.json --tool ./belenios-runtime/belenios-tool
```

Submit the encrypted JSON to the election operator and keep the returned
`ballot_sha256` tracker. The command works offline. A verified ballot file
still needs to reach the operator before voting closes. After closure, add
`--ballot-sha256 "$TRACKER"` to the tally command below. Its
`ballot_included` field reports whether the verified count contains that ballot.

For a single public Belenios 3.3.0 referendum, supply its original setup archive,
its closed archive, the setup digest retained independently before voting, and
the separately established eligible population. The command verifies the
ballots, decryption and result, reads the question from the pinned setup, and
applies the same two-thirds rule used in the Citizen procedure. It supports one
Ed25519 Yes/No/Abstain question with one unweighted credential per registered
participant. The result lists abstentions and separately counts eligible people who cast
no ballot.

```sh
python3 -B citizen.py belenios-tally initial.bel closed.bel \
  --setup-sha256 "$TRUSTED_SETUP_SHA256" --eligible 101 --tool ./belenios-runtime/belenios-tool
```

New fictional Citizen elections record the electorate size, jurisdiction,
register identifier and reference date in the public Belenios setup before the
first ballot. With an independently retained setup digest, the tally reader
uses that opening declaration. It rejects a conflicting `--eligible` argument.
Older setups require the caller's independently established population. The
public archive establishes credential and ballot counts. Legal eligibility
requires a separate registration process.

To read a published referendum from local Core storage, use its signed manifest,
the publisher public key you trust and the existing cache containing its chunks.
Citizen asks the Core CLI to reconstruct the ZIP in a temporary directory, checks
the publisher and then runs the same Belenios verification. Both steps work offline.
The trusted setup identifies the intended elections even if the same publisher
has issued another valid exercise. An expired Core manifest requires a current
publication. An already saved ZIP remains readable with `belenios-replay`.

```sh
python3 -B citizen.py belenios-replay-cache public.pb --publisher-key "$PUBLISHER_KEY" \
  --cache ./public-cache --setup-pin public-setup.json --tool ./belenios-runtime/belenios-tool
```

The ZIP contains the initial and final public Belenios archives and a Citizen
report. A reader can replay the proofs after all fictional private credentials and
trustee keys have been discarded. The exercise uses one operator for registration,
ballot generation and trusteeship. [Protocol, source and verification scope](integrations/belenios/README.md).

### Offline voter trial

On 24 November 2026, four fictional voters prepared encrypted ballots with
Belenios 3.3.0 in an offline Linux sandbox with no access to the authority's
files. The operator submitted three. After the authority directory was removed,
Citizen verified one Yes, one No and one Abstain, found the three submitted
trackers and reported the fourth absent. The runner tested PR head `a2c4f005`
against `7007a829`. The tested tree matches merged revision `1c8e6fc3`.
[Native test and run log](https://github.com/VOLPAROSSA/volparossa-citizen/actions/runs/45408384173/job/138495180143)
· [Merged source](https://github.com/VOLPAROSSA/volparossa-citizen/commit/1c8e6fc32702aac666d0730fc48feabca0ae79a6).

The same run published the three library-hours demonstration archives and
their separate public setup digests for replay.
[Public referendum bundle](https://github.com/VOLPAROSSA/volparossa-citizen/actions/runs/45408384173/artifacts/14927331791)
· [Public setup digests](https://github.com/VOLPAROSSA/volparossa-citizen/actions/runs/45408384173/artifacts/14926588801).

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
A closed report retains the account and support counts seen at closing. Later
registrations are available to a new procedure. Each repeat starts with a
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
- [x] Offline Belenios archive verification and altered-result rejection for three synthetic referenda.
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

Citizen is evaluating the following projects for its application-specific workflows.

- [Decidim](https://docs.decidim.org/en/develop/features/general-description.html)
  separates participation spaces and components such as proposals and meetings.
  It is a candidate for deliberation workflows, not a decentralized transport layer.
- [AnonCreds Rust](https://github.com/anoncreds/anoncreds-rs) implements anonymous
  credential handling. It is a candidate for a later credential adapter; issuance
  trust and complete electorate coverage remain separate problems.
- Belenios supplies the optional external cryptographic verifier for the fictional
  library-hours exercise. The project documents the assumptions around voting
  devices, coercion and the roles of its authorities. [Belenios FAQ](https://www.belenios.net/faq.html).

Original Citizen source uses GPL-3.0-only. The external tools retain their source
licenses and notices. [Citizen license](LICENSE).
