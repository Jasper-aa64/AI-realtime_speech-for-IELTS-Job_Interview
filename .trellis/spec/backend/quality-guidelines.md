# Quality Guidelines

> Code quality standards for backend development.

---

## Overview

Backend changes must preserve independent build targets and keep feature
contracts testable through CMake/CTest. When a feature crosses data files,
external command-line tools, reports, and runtime services, document and test
the boundary behavior instead of relying only on manual end-to-end runs.

## Scenario: IELTS Speaking CLI Simulator

### 1. Scope / Trigger

- Trigger: This feature adds a new executable, runtime data contracts, external
  CLI integrations, and generated JSON reports.
- Scope: `IELTSSpeakingSimulator`, `src/ielts/`, `include/ielts/`,
  `data/ielts/`, `reports/ielts_*.json`, and CMake/CTest wiring.

### 2. Signatures

- Build target: `IELTSSpeakingSimulator`
- Smoke test target: `ielts_data_test`
- CLI entry:
  ```bash
  ./IELTSSpeakingSimulator [--data-dir data/ielts] [--reports-dir reports] [--config config/default_config.json]
  ./IELTSSpeakingSimulator --help
  ```
- Question bank:
  ```cpp
  void QuestionBank::LoadPart1(const std::string& data_dir);
  void QuestionBank::LoadPart2(const std::string& data_dir);
  std::vector<P1Question> QuestionBank::SampleP1Questions(int n = 5) const;
  P2Topic QuestionBank::SampleP2Topic() const;
  ```
- Scoring:
  ```cpp
  IELTSScore Scorer::Score(const std::string& transcript);
  ```

### 3. Contracts

- Part 1 files live under `data/ielts/part1/*.json`:
  ```json
  {
    "season": "2025-autumn",
    "part": 1,
    "topic": "family",
    "questions": ["Do you live with your family?"]
  }
  ```
- Part 2 files live under `data/ielts/part2/*.json`:
  ```json
  {
    "season": "2025-autumn",
    "part": 2,
    "topics": [
      {
        "title": "Describe a book you recently read",
        "bullets": ["What it was about"],
        "p3_theme": "reading_habits"
      }
    ]
  }
  ```
- Prompt files are required:
  - `data/ielts/prompts/scorer_system.md`
  - `data/ielts/prompts/p3_question_gen.md`
- Reports are written as `reports/ielts_YYYYMMDD_HHMMSS.json` and include:
  `timestamp`, `candidate`, `parts`, `overall.band`, and per-part transcript
  and score objects when that part was run.
- Overall IELTS band is recomputed locally from the four scoring dimensions and
  rounded upward to the next 0.5. Do not trust a model-provided overall value.

### 4. Validation & Error Matrix

- Missing `data/ielts/part1` or `part2` directory -> throw a runtime error with
  the missing path.
- Malformed JSON -> throw a runtime error naming the file.
- Part 1 file with non-array `questions` -> throw a runtime error.
- Part 2 file with non-array `topics` -> throw a runtime error.
- Empty loaded Part 1 or Part 2 bank -> throw a runtime error before the exam
  starts.
- Codex/Claude CLI unavailable, non-zero, or empty output -> log the failure and
  use deterministic fallback scoring/questions where the session can continue.
- Report or WAV write failure -> throw a runtime error; do not silently ignore
  failed output writes.

### 5. Good/Base/Bad Cases

- Good: A new `data/ielts/part1/YYYY_season_topic.json` file is added; no code
  changes are needed and the next run can sample it.
- Base: `IELTSSpeakingSimulator --help` works without connecting to realtime
  services.
- Bad: A session hardcodes `reports/` instead of using `--reports-dir`; this
  breaks testability and user-selected output locations.

### 6. Tests Required

- CMake configure must succeed from a clean build directory.
- `IELTSSpeakingSimulator` target must build.
- `IELTSSpeakingSimulator --help` must exit successfully.
- `ielts_data_test` must load bundled Part 1, Part 2, and prompt files and
  assert non-empty sampled data.
- `ctest --output-on-failure` should pass for the configured build directory.

### 7. Wrong vs Correct

#### Wrong

```cpp
std::ofstream wav("reports/part2.wav");
wav << bytes; // no error check
```

#### Correct

```cpp
std::filesystem::create_directories(reports_dir);
std::ofstream wav(path, std::ios::binary);
if (!wav) {
    throw std::runtime_error("Failed to write IELTS WAV recording: " + path.string());
}
```

---

## Forbidden Patterns

- Do not make terminal-only targets depend on Qt sources or widgets.
- Do not hardcode runtime output paths inside session classes; pass configured
  directories through the manager/session constructor.
- Do not silently ignore failed file writes for reports, recordings, or prompt
  artifacts.
- Do not let LLM-generated JSON scores define `overall_band`; recompute it from
  the validated dimensions.

---

## Required Patterns

- Use CMake targets for buildable units and register smoke tests with CTest.
- Keep data-driven features reloadable through files under `data/` without
  requiring recompilation.
- Shell-out integrations must have a deterministic fallback or a clear runtime
  error, depending on whether the user flow can safely continue.

---

## Testing Requirements

- Every new executable target needs at least a build check and a no-service
  smoke path such as `--help`.
- Every bundled runtime data contract needs a test that loads representative
  files and asserts the minimum fields required by the application.

---

## Code Review Checklist

- Does the new target avoid unrelated UI or legacy feature sources?
- Are user-configured paths respected through all layers?
- Are external CLI failures handled explicitly?
- Are JSON file formats validated at load time?
- Can the core target and its smoke/data tests run without live credentials?
