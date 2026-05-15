# Directory Structure

> How backend code is organized in this project.

---

## Overview

This repository is a single C++17 application with separate CLI/GUI entry
points and feature modules under `src/` plus public headers under `include/`.
New non-Qt backend features should be implemented as focused modules that can
be linked into a dedicated executable target without pulling in Qt UI code.

The repository is also gaining a Django backend scaffold under
`backend_django/`. Keep that scaffold organized around explicit Django apps and
thin API adapters so business rules remain testable outside request handling.

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

## Django Backend Scaffold

The Django backend lives under `backend_django/` and should keep project
configuration, domain apps, and dependency lists separate:

```
backend_django/
├── config/          # Django settings, URL routing, ASGI/WSGI entry points
├── apps/
│   ├── accounts/    # users, auth, profiles
│   ├── speaking/    # IELTS speaking sessions, attempts, reports
│   ├── writing/     # IELTS writing workflows
│   ├── billing/     # wallet, recharge, balance, transactions
│   ├── ai/          # model clients, prompts, scoring/coaching adapters
│   └── common/      # shared models, permissions, pagination, utilities
└── requirements/    # dependency groups such as base/dev/prod
```

- Put Django project settings, root URL routing, and deployment entry points in
  `backend_django/config`.
- Keep domain behavior inside the relevant app under `backend_django/apps/`.
  For example, AI orchestration belongs in `backend_django/apps/ai`, while
  speaking session state belongs in `backend_django/apps/speaking`.
- Use each app's `services.py` for business logic and orchestration that should
  be callable from views, background jobs, and tests.
- Keep `views.py` focused on API adapter responsibilities: request parsing,
  authentication/permission checks, serializer use, service calls, and response
  shaping.
- Store migrations in each app's `migrations/` directory. Do not centralize
  migrations across domains.
- Use `requirements/` for dependency groups rather than a single growing
  requirements file when environments diverge.

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
