# Directory Structure

> How backend code is organized in this project.

---

## Overview

This repository is a single C++17 application with separate CLI/GUI entry
points and feature modules under `src/` plus public headers under `include/`.
New non-Qt backend features should be implemented as focused modules that can
be linked into a dedicated executable target without pulling in Qt UI code.

---

## Directory Layout

```
src/
├── common/       # shared config, logging, protocol, and state utilities
├── services/     # reusable infrastructure such as audio, realtime, LLM, PDF
├── interview/    # original technical interview flow
├── ielts/        # IELTS speaking simulator flow
├── ui/           # Qt widgets only
├── main.cpp      # original CLI entry
├── main_ielts.cpp
└── main_qt.cpp

include/
├── common/
├── services/
├── interview/
├── ielts/
└── ui/

data/
└── ielts/        # bundled IELTS question banks and LLM prompts
```

---

## Module Organization

- Keep feature-specific orchestration in its own namespace and directory,
  mirroring `src/<feature>/` with `include/<feature>/`.
- Put reusable infrastructure in `services/` only when it is independent of a
  product flow. Feature logic such as IELTS scoring, report generation, and
  session sequencing belongs in `src/ielts/`, not `src/services/`.
- CLI entry points should be thin: parse flags, construct config/services, and
  call a manager class.
- Avoid linking Qt sources into terminal targets. Qt-only code stays under
  `src/ui/` and `include/ui/`.

---

## Naming Conventions

- Use lowercase snake_case for C++ file names: `part2_session.cpp`,
  `question_bank.h`.
- Use PascalCase for classes and structs: `IELTSManager`, `QuestionBank`.
- Use `k`-prefixed enum constants for scoped enums: `ExamMode::kFullExam`.
- Data files should include the domain and season in the file name when they
  are externally replaceable, for example `2025_autumn_family.json`.

---

## Examples

- IELTS CLI target:
  - `src/main_ielts.cpp`
  - `src/ielts/*.cpp`
  - `include/ielts/*.h`
  - `data/ielts/**`
- Original interview flow:
  - `src/interview/*.cpp`
  - `include/interview/*.h`
