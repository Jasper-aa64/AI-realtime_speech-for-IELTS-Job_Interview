# CHANGES

## Summary

Added a software construction deliverables index and a single validation entrypoint that verifies the experiment 1-5 file set and runs the experiment 2-5 validation scripts.

## Files Changed

- `软件构造/README.md`
- `scripts/run_software_construction_deliverables_validation.sh`
- `软件构造/软件构造_实验1_报告.docx`
- `软件构造/软件构造-实验2.pptx`
- `软件构造/软件构造-实验3.pptx`
- `软件构造/软件构造-实验4.pptx`
- `软件构造/软件构造-实验5.pptx`
- `.trellis/tasks/05-30-finalize-software-construction-deliverables-index/prd.md`
- `.trellis/tasks/05-30-finalize-software-construction-deliverables-index/implement.jsonl`
- `.trellis/tasks/05-30-finalize-software-construction-deliverables-index/check.jsonl`

## Validation

```text
bash -n scripts/run_software_construction_deliverables_validation.sh
scripts/run_software_construction_deliverables_validation.sh

Software construction deliverables validation passed.
```

## Behavior Notes

- No product UI, backend API, scoring, prompt, database schema, or runtime behavior changed.
- Existing unrelated dirty files were preserved.
- Generated WASM artifacts remain ignored by git.
