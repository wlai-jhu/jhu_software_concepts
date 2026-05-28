Name: Wade Lai
JHED ID: wlai8

Module Info:
Module 2 - Assignment: Web Scraping
Title: Grad Cafe Applicant Data Scraper
Due Date: May 31, 2026
Repository SSH URL: git@github.com:wlai-jhu/jhu_software_concepts.git

Approach:
This module is organized as a small Python scraping and cleaning package. All assignment
materials are stored inside the module_2 folder.

The scraper is implemented in scrape.py. It uses urllib to construct Grad Cafe URLs,
request robots.txt, inspect whether the configured public Grad Cafe results URL may be
scraped, and request public result pages. The default target is 50,000 applicant records.
The scraper uses BeautifulSoup and regular expressions to identify applicant entries,
preserve the original raw listing text, and extract structured fields such as program,
university, status, decision dates, term, student origin, GRE metrics, GPA, degree, comments,
and source URL. The scraper includes a configurable delay between page requests and stops
if the site returns blocking, rate-limit, or server rejection status codes such as 403, 429,
or repeated 5xx responses. Transient server errors such as HTTP 522 are retried with
configurable backoff. The scraper saves checkpoint output after each successfully parsed
page so partial progress is preserved if the site later rejects or times out.

The scraper can also use Selenium as an optional rendering tool if Grad Cafe pages require
browser rendering. Selenium is controlled by passing --selenium when running scrape.py.
The Selenium workflow uses Chrome through Selenium Manager and an explicit wait for the
page body before collecting page_source for BeautifulSoup parsing. Selenium is not used to
bypass robots.txt, login requirements, CAPTCHAs, access controls, or rate limits.

The cleaning step is implemented in clean.py. It loads raw scraped records, removes HTML
tags/entities, standardizes obvious school-name variants, preserves the original raw text,
and writes valid JSON to applicant_data.json. The cleaning script also creates cleaned
program and university fields while keeping the original scraped values for traceability.
Applicant status values include Accepted, Rejected, Waitlisted, and Interview when those
statuses are present in the public Grad Cafe table.

The optional comment enrichment step is implemented in enrich_comments.py. The public
survey table does not always include applicant comments, so this script politely visits
public /result/ detail pages, reads the public admission notes field, and adds comments
when notes are available. It uses urllib, BeautifulSoup, a configurable delay, progress
metadata, 16-way detail-page batches by default, and stop conditions for blocking or
server errors. The submitted applicant_data.json and llm_extend_applicant_data.json files
include detail-page comments recovered by this enrichment step.

The assignment-provided local LLM hosting package is stored under:
module_2/llm_hosting

The integration wrapper is implemented in llm_clean.py. It converts scraped records into
the input format expected by llm_hosting/app.py, runs the local LLM command line interface,
reads the JSONL output, merges llm_generated_program and llm_generated_university back
into the applicant records, and writes llm_extend_applicant_data.json. The original
program_name, university, and raw_text fields are preserved for traceability.

Robots.txt Evidence:
Before scraping, run:
python scrape.py --check-robots-only

This writes the fetched robots.txt text to:
evidence/robots_check.txt

Also save a browser screenshot of the robots.txt page as:
evidence/screenshot.jpg

The evidence folder also includes evidence/README.txt, which explains what
screenshot.jpg shows and how it supports robots.txt compliance.

Robots.txt was checked using urllib. The saved robots_check.txt permits User-agent: *
for public pages with Allow: / and disallows private/account pages such as /signin,
/register, /profile, and password reset pages. The scraper refuses to scrape the
configured target if robots.txt does not permit it.

Install:
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt

module_2/requirements.txt also installs the local LLM package dependencies listed in
llm_hosting/requirements.txt.

Run:
.venv/bin/python scrape.py --target 50000 --delay 3 --output data/raw_applicant_data.json
.venv/bin/python clean.py --input data/raw_applicant_data.json --output applicant_data.json

By default, scrape.py fetches 16 public survey pages at the same time, then parses and
saves results in page order so the JSON output stays deterministic. The --parallel-pages
option can lower or raise the number of concurrent survey pages. The scraper still checks
robots.txt before scraping, saves progress after each batch, applies retry and backoff
behavior, and stops if the site blocks, rate-limits, or rejects requests. Selenium mode
stays single-page because launching many browser instances at once would be less polite
and less reliable.

The scraper also removes duplicate applicant records before saving. It treats the public
/result/ entry URL as the stable record key when available and falls back to raw_text when
an entry URL is unavailable. If duplicates are skipped during a run, scraping continues
until the target number of unique records is reached or the site asks the scraper to stop.

If Grad Cafe returns a temporary server error, increase retry/backoff settings:
.venv/bin/python scrape.py --target 50000 --delay 5 --max-retries 5 --backoff 30 --output data/raw_applicant_data.json

Resume options:
- The scraper writes progress metadata next to the output file. For example,
  data/raw_applicant_data.progress.json stores the last successful page and next page.
- To automatically continue from the saved progress file:
  .venv/bin/python scrape.py --target 50000 --delay 5 --max-retries 5 --backoff 30 --resume --output data/raw_applicant_data.json
- To manually resume near a known stopping point:
  .venv/bin/python scrape.py --target 50000 --delay 5 --max-retries 5 --backoff 30 --start-page 1200 --resume --output data/raw_applicant_data.json

Run with local LLM standardization:
cd llm_hosting
../../.venv/bin/python -m pip install -r requirements.txt
cd ..
../.venv/bin/python llm_clean.py --input data/raw_applicant_data.json --output llm_extend_applicant_data.json

The LLM workflow writes intermediate files to:
data/llm_input.json
data/llm_output.jsonl

If the local LLM process is interrupted, resume it without reprocessing completed rows:
../.venv/bin/python llm_clean.py --input data/raw_applicant_data.json --output llm_extend_applicant_data.json --resume-llm

For shorter repeatable resume runs, process the next batch of uncompleted rows:
../.venv/bin/python llm_clean.py --input data/raw_applicant_data.json --output llm_extend_applicant_data.json --resume-llm --llm-batch-size 1000

Validate final JSON deliverables:
../.venv/bin/python validate.py

The validator loads applicant_data.json and llm_extend_applicant_data.json, confirms each
file has at least 50,000 records, and prints coverage counts for the required fields.

Run a 95% confidence sample audit:
../.venv/bin/python audit_sample.py --file applicant_data.json --confidence 0.95 --margin 0.05 --seed 20260528 --sample-output data/audit_sample_applicant_data.json
../.venv/bin/python audit_sample.py --file llm_extend_applicant_data.json --confidence 0.95 --margin 0.05 --seed 20260528 --sample-output data/audit_sample_llm_extend.json

The sample audit calculates the finite-population random sample size needed for the
requested confidence level and margin of error, saves the sampled records for manual
review, and runs automated checks for required keys, missing core fields, source links,
status/date consistency, raw HTML remnants, and plausible numeric ranges. With 50,000
records, the default 95% confidence and 5% margin of error samples 382 records.

Optional comment enrichment:
../.venv/bin/python enrich_comments.py --input applicant_data.json --output applicant_data.json --max-detail-pages 200 --delay 1

To check every applicant detail page for comments when available:
../.venv/bin/python enrich_comments.py --input applicant_data.json --output applicant_data.json --all-records --parallel-pages 16 --delay 1 --save-every 25 --progress data/comment_enrichment.progress.json

The all-records run checks each public /result/ page that does not already have a comment.
By default it fetches 16 public detail pages at a time, updates comments from the public
admission notes field when available, writes progress to the selected progress JSON file,
and checkpoints the output JSON every 25 checked detail pages. The command is designed to
be interrupted and resumed with --resume using the same --progress path.

The submitted JSON files include comments recovered from checking all 50,000 public
detail-page links when a public admission notes field was available. At submission time,
comments are available for 23,865 records in both applicant_data.json and
llm_extend_applicant_data.json.

Systematic Cleaning Edge Cases:
- Some Grad Cafe rows do not expose comments in the survey table view, so enrich_comments.py
  checks public detail pages for the admission notes field. Many entries still have no
  applicant-provided notes, so comments remain None when no public notes are available.
- Some school names are user-entered or abbreviated, and the tiny local LLM occasionally
  introduces capitalization or accent artifacts. The final JSON preserves original
  program_name, university, and raw_text fields so these cases can be traced and improved.
- If the LLM output is partial, llm_clean.py keeps deterministic cleaned values for
  unprocessed rows and fills LLM fields with those fallback values so the JSON remains
  consistent. This means every submitted row has standardized program and university
  fields, even when the local LLM did not finish processing that exact row.
- The current local LLM run generated completed LLM standardization output for 7,625
  applicant records. llm_clean.py can continue from that point with --resume-llm, and the
  submitted llm_extend_applicant_data.json still contains standardized fields for all
  50,000 rows by combining available LLM output with deterministic fallback cleaning.

Known Bugs:
Grad Cafe page structure may change, so the selectors in scrape.py may need adjustment if
the scraper reports zero applicant records. If that happens, inspect a saved page source,
identify the result container CSS class or table row structure, and update _candidate_entries()
or _parse_entry() accordingly. The regex-based parser is intentionally conservative and may
leave some fields as None when the source text is inconsistent. Those records still preserve
raw_text for reproducibility.
