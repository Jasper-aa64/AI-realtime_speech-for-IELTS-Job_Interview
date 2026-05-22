# Cambridge IELTS writing prompt import

This directory is for user-provided, authorized Cambridge IELTS Writing materials.

Do not commit copyrighted Cambridge prompt text or chart images here unless the project has the right to distribute them. The app will automatically import JSON files from:

- `data/ielts/writing/cambridge/task1_academic/**/*.json`
- `data/ielts/writing/cambridge/task2/**/*.json`

`cambridge_1_20_manifest.json` contains the complete Cambridge IELTS Writing slot catalog for books 20 down to 1, tests 1-4, Task 1 and Task 2. The UI uses it to show IDs such as `剑雅20-1 Task 1` and `剑雅20-1 Task 2` even before authorized prompt text/images have been imported.

Task 1 records should include an `image_url` that points to a served asset, for example `/assets/writing/task1/cambridge/20/test_1_task_1.png`.

Example file:

```json
{
  "task_type": "task1_academic",
  "source": "cambridge_ielts",
  "book": 20,
  "test": 1,
  "prompts": [
    {
      "id": "cambridge-20-test-1-task-1",
      "title": "Cambridge IELTS 20 Test 1 Task 1",
      "category": "line_graph",
      "source_question": 1,
      "image_url": "/assets/writing/task1/cambridge/20/test_1_task_1.png",
      "prompt": "Paste authorized prompt text here."
    }
  ]
}
```

Supported Task 1 categories: `line_graph`, `bar_chart`, `pie_chart`, `table`, `map`, `process`, `mixed`.

Supported Task 2 categories: `opinion`, `discussion`, `problem_solution`, `advantages_disadvantages`, `two_part`.

The prompt picker sorts Cambridge records by book descending, so book 20 appears before 19, down to 1.

## Authorized batch import

Use `scripts/import_cambridge_writing_materials.py` when you have local, authorized Cambridge Writing prompt text and Task 1 chart images.

The importer:

- validates each item against `cambridge_1_20_manifest.json`
- copies Task 1 images into `web/static/assets/writing/task1/cambridge/<book>/`
- optionally normalizes image contrast/sharpness and max dimensions
- writes app-loadable JSON files under `data/ielts/writing/cambridge/<task_type>/`

It intentionally does not download materials and does not remove watermarks.

Import example:

```powershell
python scripts/import_cambridge_writing_materials.py C:\path\to\authorized_cambridge_materials.json
```

Check current coverage:

```powershell
python scripts/import_cambridge_writing_materials.py --manifest-report
```

Use `data/ielts/writing/cambridge/example_authorized_materials.json` as a starter template.

Input JSON:

```json
{
  "materials": [
    {
      "id": "cambridge-20-test-1-task-1",
      "task_type": "task1_academic",
      "book": 20,
      "test": 1,
      "source_question": 1,
      "title": "Cambridge IELTS 20 Test 1 Task 1",
      "category": "line_graph",
      "prompt": "Paste authorized prompt text here.",
      "image_path": "images/c20_t1_task1.png"
    }
  ]
}
```
