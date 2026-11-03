# Linha do Tempo da Urna

An interactive, chronological map of the public Brazilian electronic-voting data (TSE), built so anyone can run
their own independent analysis. The site only **shows the published data as is** and surfaces patterns; it never
estimates, weights or interprets results.

- `site/` – static web app (no build step). Open with any static server, e.g. `cd site && python3 -m http.server`.
- `pipeline/` – scripts that download, parse and verify the TSE files and write the site's data.

## What the site shows

| Phase | Map colour | Source |
|---|---|---|
| Voting day (08:00 → last urna closed) | Neutral teal scale: turnout, share of votes without biometrics, or share of "fast" votes, as of the selected minute | Urna logs (`logd.dat`), one event per voter with timestamp |
| Count (first → last BU received) | Red (Lula) ↔ blue (Flávio Bolsonaro) with a light neutral midpoint; each urna is added at the minute the TSE received its Boletim de Urna | BU files (`DT_BU_RECEBIDO`) |

On every scale a **darker shade means more** (more turnout, more votes without biometrics, a larger lead).

**Votes abroad** (`ZZ`, 1,308 urnas in 144 cities) appear as one circle off the coast and are included in the
national totals. Only their BU is used: urna clocks abroad run on each city's local time and the TSE files do not
identify the time zone, so they join the timeline at the count (BU receipt time is TSE server time, Brasília).

Why the map is **not** red/blue during voting: the urna log records *that* a voter voted, never *for whom*, and the
RDV stores votes shuffled on purpose. Any minute-by-minute candidate colouring would be fabricated.

Timeline markers (all times in Brasília time): official opening (08:00) and regular closing (17:00);
**"Urnas além das filas"** = the minute by which 99% of urnas that closed before 18:00 had closed (data-derived start
of the extension window); **"Fim da prorrogação"** = the minute by which 99.99% of all urnas had closed;
**"Última urna encerrada"** names the very last urna; first and last BU received.

Urna clocks run on local time. The pipeline derives each municipality's offset from the data (urnas open at 08:00
Brasília, so the local opening hour gives the offset), which covers Acre, western Amazonas, MT, MS, RO, RR and
Fernando de Noronha without a hand-made table.

### "Sem biometria"

Everywhere on the site, *sem biometria* = fingerprint read failed and a mesário released the voter **plus** voters for
whom the urna did not ask for a fingerprint.

### The extension ("Prorrogação")

`pipeline/late_votes_table.py` counts, per urna, the votes cast after each cutoff (17:00 … 19:00, Brasília) and how
voters were enabled; `pipeline/analyze_extension.py` derives exact hard-stop bounds (removing every late vote, all for
one candidate or all for the other), where the extended urnas were, the biometric profile vs. the same urnas'
16:00–17:00 voters, and clearly-labelled statistical estimates. Results: the **Prorrogação** map view, the
"Parada às 17:00" timeline milestone, `site/prorrogacao.html` and `docs/relatorio_prorrogacao.md`.

### Conferências das urnas (files, signatures, RDV × BU) and statistical signals

`pipeline/verify_urnas.py <UF> site <out>` downloads, for every urna, only its own members of the TSE `arqurnatot`
package (HTTP range requests) and checks: the SHA-512 of BU, RDV, BU image and log against the list signed by the
software and by the urna; the self-hash of each signed list; the urna's certificate (issuer, validity on election
day, serial = internal urna number in the BU); BU and RDV decoded (2026 layouts in `pipeline/spec/`); RDV = BU vote by
vote; BU = bweb; habilitations = attendance. The signature *values* (CEPESC; Ed521-style) cannot be checked with
public documentation and are reported as such. `pipeline/anomaly_scan.py` computes per-urna statistical signals from
the logs and `pipeline/summarize_checks.py` writes `site/data/conferencias.json.gz` and the CSVs in
`site/data/conferencias/`, shown on `site/conferencias.html`. A flagged urna is a pattern to check, not proof.

### "Fast votes"

A vote without biometrics is flagged as fast when it meets all three user-chosen limits: (1) time from the first
fingerprint request to the manual-release request, (2) time until the mesário's fingerprint released the voter,
(3) time from release to the computed vote. The panel always shows the same speed measure (3) among
fingerprint-verified voters for comparison, plus the medians of each step. A fast vote is a pattern to check, not
evidence of wrongdoing.

## Data and verification

For every urna the pipeline checks the log against the BU of the same section: number of voters and number of
"não habilitados por biometria". Results per state are in `site/data/<UF>/summary.json` and in the site's "Sobre"
dialog, which lists every urna where log and BU differ. Log-reading rules learned from the data:

- packages of replaced (contingency) urnas contain archived logs, sometimes twice: exact duplicate lines are dropped;
- a package can include the log of an urna loaded for *another* section: only votes from urnas loaded for the
  package's own section are counted;
- a vote confirmed right before an urna restart has no "computado" line; the BU sometimes counts it and sometimes
  not, so per urna the pipeline follows the BU and reports how many such votes were dropped.

Mesário título numbers that appear in the logs are never published (in-memory salted hashes only).

## Running the pipeline

```bash
pip install pandas pyarrow shapely && npm install mapshaper@0.6.102
# 1. per state: download + verify the BU CSV (SHA-512), index the urna-files zip and parse every urna log
#    (HTTP range requests; the multi-GB zips are never stored). Resumable.
python pipeline/fetch_all.py <workdir> RR,AP,AC,...,SP 4
# 2. build each state's site data (municipal shapes, sources) and the national manifest
python pipeline/build_all.py <workdir> site node_modules/mapshaper/bin/mapshaper
```

Status: all 27 states + votes abroad, 2nd round (Presidente).
