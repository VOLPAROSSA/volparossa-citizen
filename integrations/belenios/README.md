# Verifying the library-hours referenda

The generator issues Belenios credentials to five registered fictional residents
in an electorate of six. Two different supporters open each vote. The question
permits exactly one answer among yes, no and abstain. Citizen checks eligibility
and refuses repeat submissions before the harness generates another encrypted
ballot. Belenios itself supports revoting. Each case has fresh randomness, its
own election identifier, a credential authority and a single decryption trustee.

| Case | Yes | No | Abstain | Did not vote | Citizen decision |
| --- | ---: | ---: | ---: | ---: | --- |
| Adoption | 4 | 0 | 1 | 1 | Four yes out of six |
| Indeterminate | 3 | 0 | 1 | 2 | Neither side reached four |
| Rejection | 1 | 4 | 0 | 1 | Four no out of six |

## What the checks establish

Belenios checks the ballots, tallies their ciphertexts and checks the trustee's
decryption proof against the published result. For each election the generator
also uses Belenios' event writer to move one yes vote to no in the published result.
The altered total is internally plausible and preserves turnout. The native verifier must reject it specifically during result verification.
Only the original accepted archives enter the bundle.

The separate replay command takes the public ZIP and the original external tool.
It runs `election verify-diff` from each setup archive to its final archive,
requires a closed result, reads the verified question and answer order, recomputes
the tally and counts ballots and issued credentials. It checks the Citizen report
against the declared six-person fixture. The identities, electorate completeness,
support counts and decision thresholds are supplied by the application. A reader
auditing an actual election would also need a trusted, independently retained
setup fingerprint to authenticate the election they intended to observe.

The fictional choices are published in the table above. One local process
generates the voter secrets, casts the ballots and runs the trustee. This exercise
establishes neither real-person eligibility nor secrecy against the simulation
operator. Independent administration, real voting devices, coercion resistance,
jurisdiction and legal authority remain outside its scope. Only the public proof
bundle, including the encrypted ballots, is uploaded by the manually triggered
Actions workflow or its integration-change check.

## Reproducing the verification

The commands in the main README generate and replay all cases. To inspect a
single case from a bundle you generated or downloaded from this workflow, unpack
it into a fresh directory and run the upstream verifier directly. It expects one
`.bel` archive per directory.

```sh
mkdir review
unzip -q public-referenda.zip -d review
./belenios-runtime/belenios-tool election verify-diff --dir1 review/adopted/setup --dir2 review/adopted/final
./belenios-runtime/belenios-tool election compute-result --dir review/adopted/final
```

The hosted job acquires its runtime before starting the exercise. Generation and
public replay run as an unprivileged user in a fresh Linux network namespace
with only the loopback interface. File digests vary between elections because the
tool generates fresh secrets. [Workflow](../../.github/workflows/belenios-offline.yml).

## Retain an independently authenticated setup

`citizen.py belenios-demo --setup-pin public-setup.json` writes a separate 307-byte
JSON file containing the SHA-256 digests of all three initial public archives.
The file is complete before the first ballot and an existing path is preserved.
The final ZIP contains the ballot proofs and election results. Obtain the setup
file through a separately trusted channel. Receiving it alongside an untrusted
ZIP would allow a different complete election to present its own setup.

On Citizen `f28c7988`, the independently pinned opening of each fictional
referendum included six eligible residents in `sim-town-roll` at
`2026-01-01T00:00:00Z`. Five credentials were issued. The adoption case had four
yes ballots, one abstention and one eligible resident who did not vote. The
ordinary tally reader used the opening to set the threshold at four and refused
an override of seven eligible residents after closing. Each archived opening
digest matches the corresponding initial Belenios file. The exercise operates
with a declared fictional population.
[Original public Belenios archives](../../docs/evidence/citizen-45520183577-referenda.zip) ·
[Original opening pins](../../docs/evidence/citizen-45520183577-setup.zip) ·
[Original verified count](../../docs/evidence/citizen-45520183577-tally.zip) ·
[Hosted native trial](https://github.com/VOLPAROSSA/volparossa-citizen/actions/runs/45520183577)

An owner with an existing VOLPAROSSA identity can sign the setup using the
ordinary Core CLI. Choose a new cache and manifest path. The identity key is
encrypted and Core prompts for its passphrase.

```sh
volparossa content publish --identity /path/to/identity.key --input public-setup.json \
  --cache public-setup-cache --manifest public-setup.pb --revision 1 \
  --name citizen-fictional-library-setup --content-type application/json
```

A reader with the intended manifest, verified cache and independently trusted
publisher public key can reconstruct the setup and replay the referendum.
The following commands work offline. For an election with several publications,
retain the intended manifest digest separately as well.

```sh
volparossa content assemble --manifest public-setup.pb --publisher-key "$PUBLISHER_KEY" \
  --cache public-setup-cache --output checked-setup.json
python3 -B citizen.py belenios-replay public-referenda.zip --setup-pin checked-setup.json \
  --tool ./belenios-runtime/belenios-tool
```

## External software and provenance

Belenios 3.3.0 is the upstream release tagged at commit
`337887bd1862c7cd057080b530fd80941bfc3c69`. Its opam recipe builds the CLI
with Dune and the release documents source builds in `INSTALL.md`. Inria and CNRS
copyright the upstream program. Debian records AGPL-3.0-or-later with an OpenSSL
linking exception. The helper calls a separate, unmodified executable.
[Upstream source](https://gitlab.com/vcast.vote/belenios/-/tree/337887bd1862c7cd057080b530fd80941bfc3c69)
· [Build recipe](https://gitlab.com/vcast.vote/belenios/-/blob/337887bd1862c7cd057080b530fd80941bfc3c69/belenios-tool.opam)
· [Upstream installation](https://gitlab.com/vcast.vote/belenios/-/blob/337887bd1862c7cd057080b530fd80941bfc3c69/INSTALL.md)
· [Debian copyright](https://sources.debian.org/src/belenios/3.3.0%2Bdfsg-1/debian/copyright/).

The Linux amd64 package is Debian `belenios-tool 3.3.0+dfsg-1`. Its six runtime
libraries, the loader and the tool unpack into the requested directory; preparation
does not install system packages. Package paths, lengths and SHA-256 digests were
taken from Debian's signed forky release dated 2026-11-18 20:07:19 UTC. The
`main/binary-amd64/Packages.xz` digest is
`4c714e61a0626e468aac93e23f61ae88a637df1a6ac99dae2fe637221751138a`.
Preparation verifies each download and the extracted executable. The distribution
source includes the Debian changes and the repacked original source.
[Pinned package manifest](debian-amd64.json)
· [Debian source package](https://deb.debian.org/debian/pool/main/b/belenios/belenios_3.3.0+dfsg-1.dsc)
· [Debian snapshot](https://snapshot.debian.org/package/belenios/3.3.0%2Bdfsg-1/).
