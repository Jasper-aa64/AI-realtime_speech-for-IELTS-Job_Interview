# Finalize Software Construction Deliverables Index

## Goal

Close the software construction deliverables loop by adding a single index document and validation command that make the existing experiment 2-5 architecture/refactor/TDD/reuse materials easy to audit. This task does not change product behavior.

## What I Already Know

- Experiment 2 design documents are committed:
  - `软件构造/重构总体架构.md`
  - `软件构造/实验2_设计文档.md`
  - `软件构造/实验2_类图.puml`
  - `scripts/run_experiment2_design_validation.sh`
- Experiment 3 TDD report and validation are committed:
  - `软件构造/实验3_TDD验证报告.md`
  - `scripts/run_experiment3_tdd_validation.sh`
- Experiment 4 refactor report and validation are committed:
  - `软件构造/实验4_重构报告.md`
  - `scripts/run_experiment4_refactor_validation.sh`
- Experiment 5 reuse/WASM report and validation are committed:
  - `软件构造/实验5_开源复用与WASM方案.md`
  - `scripts/run_experiment5_reuse_validation.sh`
- Existing untracked binary deliverables are present:
  - `软件构造/软件构造-实验2.pptx`
  - `软件构造/软件构造-实验3.pptx`
  - `软件构造/软件构造-实验4.pptx`
  - `软件构造/软件构造-实验5.pptx`
  - `软件构造/软件构造_实验1_报告.docx`

## Requirements

- Add a concise `软件构造/README.md` index mapping each experiment to its report, slides, validation command, and implementation evidence.
- Add a single `scripts/run_software_construction_deliverables_validation.sh` script that verifies the deliverable file set and runs the experiment 2-5 validation commands.
- Include the existing PPT/docx deliverables in the commit so the software construction folder is self-contained.
- Do not touch current Django/frontend product dirty files.
- Do not commit `backend_django/db.sqlite3`.

## Acceptance Criteria

- [x] `软件构造/README.md` lists experiments 1-5 and the current refactor arc.
- [x] The validation script checks that markdown, PlantUML, PPTX, DOCX, and validation scripts exist.
- [x] The validation script runs experiment 2, 3, 4, and 5 validation scripts.
- [x] Existing unrelated dirty files remain untouched.
- [x] Commit contains only software construction deliverables and the validation script.

## Definition of Done

- [x] `bash -n scripts/run_software_construction_deliverables_validation.sh`
- [x] `scripts/run_software_construction_deliverables_validation.sh`
- [x] `git diff --cached --check`

## Out of Scope

- Editing the product UI or APIs.
- Fixing speaking/writing AI behavior.
- Editing or regenerating PPTX/DOCX contents.
- Cleaning unrelated dirty business files.

## Technical Notes

- This is a deliverables-index task. No web research required.
- Relevant docs already exist under `软件构造/`.
