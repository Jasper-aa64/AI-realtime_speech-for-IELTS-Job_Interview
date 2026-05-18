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
