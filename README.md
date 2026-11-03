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
| Count (first → last BU received) | Red (Lula) ↔ blue (Flávio Bolsonaro) with a grey midpoint; each urna is added at the minute the TSE received its Boletim de Urna | BU files (`DT_BU_RECEBIDO`) |

Why the map is **not** red/blue during voting: the urna log records *that* a voter voted, never *for whom*, and the
RDV stores votes shuffled on purpose. Any minute-by-minute candidate colouring would be fabricated.

Timeline markers: official opening (08:00) and regular closing (17:00); **"Urnas além das filas"** = the minute by
which 99% of urnas that closed before 18:00 had closed (data-derived start of the extension window); **"Fim da
prorrogação"** = last urna closed; first and last BU received.

### "Fast votes"

A vote without biometrics is flagged as fast when it meets all three user-chosen limits: (1) time from the first
fingerprint request to the manual-release request, (2) time until the mesário's fingerprint released the voter,
(3) time from release to the computed vote. The panel always shows the same speed measure (3) among
fingerprint-verified voters for comparison, plus the medians of each step. A fast vote is a pattern to check, not
evidence of wrongdoing.

## Data and verification

For every urna the pipeline checks the log against the BU of the same section: number of voters and number of
"não habilitados por biometria". The result is written to `site/data/<UF>/validation.json` and shown in the site's
"Sobre" dialog. Mesário título numbers that appear in the logs are never published (in-memory salted hashes only).

## Running the pipeline for a state

```bash
pip install pandas pyarrow shapely
# 1. index the remote zip, then parse every urna log (range requests; the 9 GB file is never stored)
python pipeline/index_zip.py <arqurnatot zip URL> <index.pkl>
python pipeline/run_full.py <workdir> <arqurnatot zip URL> <index.pkl> <out_dir>
# 2. build the site data (BU CSV + parsed logs + municipal boundaries)
python pipeline/build_site_data.py --uf BA --bweb bweb_2t_BA_*.csv --logs <out_dir> \
  --geo-mun ba_mun.json --states-geo br_states_raw.json --sources pipeline/sources/BA_2t.json --out site/
```

Status: Bahia (2nd round) is loaded; other states appear as "not loaded yet" until processed.
