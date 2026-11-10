# Decisions: feeds (branch feat/feeds)

One short entry per decision: choice, alternatives, source, and what couldn't be verified.

---

### 2026-11-11 · KEV download
- **Choice:** `requests` GET of the official CISA JSON feed, saved byte-for-byte (contract requires a
  reproducible sha256). Fallback: the `cisagov/kev-data` GitHub repo raw file (CISA-owned org).
  Both validated before saving (non-empty `vulnerabilities`, `count == len`, required entry fields).
  Atomic write (temp file + `os.replace`). If the sha256 matches the saved file, nothing is rewritten.
- **`--diff`:** lists entries whose `dateAdded` is later than the newest `dateAdded` in the snapshot
  that was on disk before this run (as the task specifies). Entries added on the same day as the
  previous newest entry would be missed; acceptable because CISA publishes the catalog in daily batches.
- **Alternatives:** the KEV CSV feed (same data, but JSON keeps `cwes`/`notes` structured);
  NVD API `hasKev` filter (rate-limited, needs extra calls, and is a copy of CISA's data, not the source).
- **Source:** https://www.cisa.gov/known-exploited-vulnerabilities-catalog (links the JSON/CSV feeds);
  https://github.com/cisagov/kev-data. Both URLs returned HTTP 200 on 2026-11-11.
- **Not verified:** how quickly the GitHub mirror trails the cisa.gov file.
