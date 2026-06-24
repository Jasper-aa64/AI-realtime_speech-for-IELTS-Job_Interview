# Writing Task 1 Import Research

Date: 2026-05-22

## Current Repository State

- Cambridge IELTS Writing slots are prepared in `data/ielts/writing/cambridge/cambridge_1_20_manifest.json`.
- Coverage check currently reports `0/160` Cambridge slots imported:
  - Task 1 Academic: `0/80`
  - Task 2: `0/80`
- Two Task 1 image previews are available from official public samples in `data/ielts/writing/public_samples/task1_academic.json`.

## Sources Checked

### idictation.cn

URL: https://www.idictation.cn/

Usefulness:

- Good candidate for manual reference because the site is focused on IELTS machine-test practice.
- The public HTML available to search/open is a front-end shell, not a stable JSON/PDF source in the current inspection.
- The current crawl did not expose a reliable material export endpoint.
- Direct navigation to `/main/book` currently redirects to `/login`, so the book index is not publicly readable without authentication.

Current decision:

- Do not build a scraper against it yet.
- If a stable export/API or locally saved materials are available later, feed them into `scripts/import_cambridge_writing_materials.py`.

### IELTSplus Cambridge Writing index

URL: https://ieltsplus.com/ielts-writing-tests

Observed:

- Lists Cambridge IELTS 20 down through older books as Writing tests.
- The page exposes a structured index that matches our manifest shape: book -> four tests -> writing.
- Search results also expose `Cambridge IELTS 20 – Writing Test 1`, which is useful as a directory reference.

Usefulness:

- Useful for verifying our slot structure and sorting.
- Not treated as an authorized source for copying text/images into this repository.

### IELTSplus Cambridge 20 Test 1 page

URL: https://ieltsplus.com/ielts-writing-tests/cambridge-20-test-1

Observed:

- The HTML shell says it is fetching prompts and images.
- The page includes a legal note saying it is not affiliated with or endorsed by IELTS owners.
- Search results show that the site uses a consistent Cambridge 20 writing test naming scheme, which is enough to validate our `剑雅20-1 Task 1` / `Task 2` slot labels.

Usefulness:

- Useful as a UI/source-shape reference.
- Not suitable as an automatic import source without a clear permission basis.

### Hugging Face Task 1 dataset

URL: https://huggingface.co/datasets/TraTacXiMuoi/Ielts_writing_task1_academic

Observed:

- Multimodal dataset with image + text fields.
- Dataset viewer shows `train` with 11.1k rows and fields such as topic, subject, image, content, score, and evaluation.

Usefulness:

- Potential source for non-Cambridge Task 1 practice materials after license review.
- Good candidate for a separate importer if we want a broad Task 1 image bank.

Current decision:

- Do not mix it into Cambridge IELTS 1-20 slots.
- Add only after confirming license and provenance.

### Cambridge official IELTS 20 excerpt

URL: https://assets.cambridge.org/97810098/14904/excerpt/9781009814904_excerpt.pdf

Observed:

- Confirms IELTS 20 is an official Cambridge practice-test book.
- Confirms Writing structure: Task 1 requires at least 150 words and about 20 minutes; Task 2 requires at least 250 words and about 40 minutes.
- Confirms Task 1 uses diagrams/data such as graphs, tables, charts, processes, objects/events, and explanations of how something works.

Usefulness:

- Good authoritative reference for product wording and task structure.
- It is an excerpt, not a full prompt/image source.

### British Council official Task 1 samples

URLs:

- https://takeielts.britishcouncil.org/take-ielts/prepare/free-ielts-english-practice-tests/writing/academic/task-1
- https://takeielts.britishcouncil.org/take-ielts/prepare/free-ielts-english-practice-tests/writing/academic-2/task-1

Observed:

- Both pages expose official Task 1 sample prompts and chart images.
- These are safe to use as preview materials and now exist locally under `web/static/assets/writing/task1/public_samples/`.

Usefulness:

- Best immediate source for the "show me two examples" requirement.
- Not a Cambridge 1-20 import source, but useful to prove the chart UI and image pipeline.

### Local sample bank already seeded in the repo

URL: `data/ielts/writing/task1_academic.json`

Observed:

- 30 task1 sample prompts are already in the repository.
- They are now surfaced in the UI as `本地样题 1`, `本地样题 2`, ... after the two official public samples.

Usefulness:

- Immediate batch-loaded demo bank for testing the writing Task 1 flow.
- Good placeholder bank until authorized Cambridge materials are supplied.

### Additional surfaced reference sites

Observed in search:

- `ieltsessaybank.com/cambridge-ielts-20/`
- `ieltsix.com/ielts/cambridge-ielts-20/writing/`
- `voxcel.org/cambridge-academic-writing/`

Usefulness:

- These pages appear to mirror Cambridge Writing prompts, explanations, or sample answers.
- They are useful as search references and for rough topic verification.

Current decision:

- Do not import them directly as Cambridge source material without explicit provenance and permission.

## Import Path

The prepared import path is:

1. Put authorized source images and prompt text into a local folder.
2. Fill `data/ielts/writing/cambridge/example_authorized_materials.json` with the real material paths and text.
3. Run:

```powershell
python scripts/import_cambridge_writing_materials.py C:\path\to\authorized_cambridge_materials.json
```

4. Check coverage:

```powershell
python scripts/import_cambridge_writing_materials.py --manifest-report
```

The importer validates Cambridge IDs against the manifest, copies Task 1 images into `web/static/assets/writing/task1/cambridge/<book>/`, normalizes image size/contrast/sharpness, and writes app-loadable prompt JSON.

For now, the repo only contains two public official preview samples, not Cambridge 1-20 prompt packs. The Cambridge import path is ready for authorized local materials when they are available.

## Boundary

Supported:

- Authorized material import.
- Image resizing, contrast normalization, sharpening, and crop-ready storage.
- Mapping every imported item to `剑雅<book>-<test> Task <number>`.

Not supported:

- Removing third-party watermarks from copyrighted scans.
- Committing Cambridge prompt text or chart images without distribution rights.
- Pretending public/non-Cambridge samples are Cambridge IELTS 1-20 materials.
