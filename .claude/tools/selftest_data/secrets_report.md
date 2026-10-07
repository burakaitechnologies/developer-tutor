# Secrets engine report: the 34 prototype samples, before and after

<!-- secrets-report old_hidden=12 old_leaks=16 new_hidden=26 new_deliberate_keeps=2 new_leaks=0 new_false_positives=0 -->

What this is: the 34 sample strings of the prototype probe (research/old-hooks.md, PROBE 2) run through
the prototype's `hide_secrets` (10 patterns) and through the new `hooks/lib/secrets.py`.
The samples are rebuilt from fragments at run time (`tools/selftest_secrets.py`); no key-shaped
literal is stored. The report is rewritten with `python tools/selftest_secrets.py --write-report`
and the self-test fails when it is out of date.

## Numbers

| Measure | Prototype | New engine |
|---|---|---|
| Secret samples hidden (of 28) | 12 | 26 |
| Real leaks (secret shown) | 16 | 0 |
| Deliberate keeps (AWS documentation examples) | 0 | 2 |
| Card number `4242 4242 4242 4242` | visible | hidden |
| Plain samples hidden by mistake (of 5) | 0 | 0 |

Reading the numbers: the prototype hid 12 of 28 secret samples and leaked 16. The new engine hides 26 and
leaks none. The 2 samples it keeps are the AWS documentation example key and its example secret
(`...EXAMPLE...`); SPEC 7.3 says documentation examples must stay visible. The prototype also
left the card number visible; the new engine hides every Luhn-valid card number with a known prefix.

Guard mode (`scan_text`) is stricter about false alarms: it also ignores keyboard-run tokens such as
`abcdefgh...` and `1234567...`, which documentation uses and real machine-made keys never contain.
Of the 28 secret samples, guard mode reports 7 as strong hits; the rest are documentation-style
examples, short passwords, prose passwords, or weak shapes (JWT, Google API key).

## Per sample

| Sample | Prototype | New (store mode) | Guard mode |
|---|---|---|---|
| anthropic | hidden | hidden | no hit |
| openai classic | hidden | hidden | no hit |
| openai proj | visible | hidden | no hit |
| gh pat ghp | hidden | hidden | no hit |
| gh oauth gho | visible | hidden | no hit |
| gh server ghs | visible | hidden | no hit |
| github_pat | hidden | hidden | no hit |
| aws AKIA (docs example) | hidden | visible | no hit |
| aws secret (docs example) | visible | visible | no hit |
| google AIza | hidden | hidden | no hit |
| slack | hidden | hidden | no hit |
| stripe live | visible | hidden | no hit |
| stripe test | visible | hidden | no hit |
| hf token | visible | hidden | no hit |
| npm | visible | hidden | no hit |
| gitlab | visible | hidden | no hit |
| jwt | visible | hidden | no hit |
| bearer | hidden | hidden | strong hit |
| db url | visible | hidden | strong hit |
| mongodb url | visible | hidden | strong hit |
| pw colon | hidden | hidden | no hit |
| pw equals quoted | hidden | hidden | no hit |
| pw short | visible | visible | no hit |
| pw sentence | visible | hidden | no hit |
| pw turkish | visible | hidden | no hit |
| private key | hidden | hidden | strong hit |
| openssh key | hidden | hidden | strong hit |
| env line | visible | hidden | strong hit |
| env line2 | visible | hidden | strong hit |
| credit card | visible | hidden | no hit |
| ordinary | visible | visible | no hit |
| ordinary2 | visible | visible | no hit |
| uuid prompt | visible | visible | no hit |
| sha | visible | visible | no hit |

## Known limits

- A password made only of lower-case letters (`correcthorsebatterystaple`) is not hidden unless it follows
  the word password in a sentence with a digit or inner capital. Shapes without a name or a prefix are not guessed.
- An unquoted password that contains `;` after the first `;` stays visible (connection strings use `;`).
- Text beyond 256 KB is replaced by a note, not scanned.
