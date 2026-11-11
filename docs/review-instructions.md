# Reviewer guide: checking Deming's test labels

Thank you for helping. Deming is tested on 60 made-up devices. For each one we wrote down the
"right answer" (its **label**). Before we can trust the test, two people other than the author
must check those labels against the vendors' public web pages. That's you. No device is real,
and you won't touch any device or network. You only read public web pages.

## What you need
- A laptop with Chrome, Edge or Firefox. Use the **same browser** the whole time.
- Two files: `blind.html` and `review.html` (in the `review/` folder). Each is a single file.
  Double-click it and it opens in your browser. No install, no login, no internet needed for the
  page itself. You do need internet to open the vendor links.
- Your initials, for example `AB`. You must type them before you can export.

## Order matters: blind first
1. **Blind labelling first (about 45 minutes).** Open `blind.html`. You'll see 15 devices, with
   only the name and firmware the owner typed. For each one, find the vendor, product and version,
   and pick a lane, using the vendor's own website or the CISA KEV catalog. Write down the page you
   used. **Do not open `review.html` until you've exported this.** If you've seen the answers,
   the blind test is spoiled.
2. **Label review second (about 2 to 3 hours; you can split it over several sittings).** Open
   `review.html`. It shows one device at a time, with the answer we wrote and why.

## The four lanes
- **patch**: the vendor still supports it, it has a known exploited vulnerability at this version, and a fix exists.
- **retire**: the vendor has stopped supporting it (past end of life). This wins even if a fix exists.
- **fine**: supported, and no known exploited vulnerability at this version.
- **unknown**: a careful person can't tell what it is, or can't decide from what's given.

Judge every date **as of 12 November 2026**.

## What to check on each device (review page)
1. Read the raw name and firmware. Do the label's vendor, product and version really describe this device?
2. Open each **source link**. Find the date or fixed version the label relies on. Does it say what the note says?
3. Is the lane right by the rules above? For example, a support end date before 12 Nov 2026 means retire.
4. Read the **Mechanical check** box. A script has already compared the label with our data files.
   - A red **flag** means the script found something odd. Look harder, but the label may still be right (some flags are known tricky cases).
   - **"needs you in a browser"** means the site blocked the script, or the page is a PDF. Only you can check that page.
   - A green "pass" does **not** mean the label is right. Check it anyway.
5. Choose one:
   - **Verified**: you checked the sources and the label is right.
   - **Disagree**: something is wrong. Say what in the notes, for example "support ended 2025, so retire, not patch".
   - **Unsure**: you couldn't confirm it, for example the page wouldn't load or you can't read the table. Say why. Unsure is a perfectly good answer: it means "don't count this as verified". Please don't guess.

The page starts in **flagged first** order. Tick "Only flagged / needs human" to see just those.
Nothing is pre-selected. A device counts only after you choose.

## Saving and exporting
- Your progress saves in your browser automatically. If a message says it can't save, export often.
- **Export CSV** downloads a file such as `deming-review-AB-20261112-1030.csv`. Export at the end,
  and any time you stop for the day.
- To continue on another day or another browser, click **Resume from an exported CSV** and pick your last export.
- Send both files (the blind export and the review export) to the team. Nothing is uploaded from the pages.

## For the team (after both reviewers finish)
```
python eval/blind/agreement.py <blind_A.csv> <blind_B.csv>
python scripts/merge_reviews.py <review_A.csv> <review_B.csv>
```
The merge writes `data/ground_truth.reviewed.csv` (the original is never changed) and lists every
row not verified by both reviewers in `docs/label-disagreements.md`. If labels change after a
review, rebuild the pages (`scripts/check_labels.py`, `scripts/build_review_page.py`) and
re-review the changed rows: the review page starts fresh when a label changes.
