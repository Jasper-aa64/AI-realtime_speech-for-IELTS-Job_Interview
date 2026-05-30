#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "== Software construction deliverables validation =="
echo "Repository: ${ROOT_DIR}"
echo

echo "== deliverable files =="
REQUIRED_FILES=(
  "软件构造/README.md"
  "软件构造/重构总体架构.md"
  "软件构造/实验2_设计文档.md"
  "软件构造/实验2_类图.puml"
  "软件构造/实验3_TDD验证报告.md"
  "软件构造/实验4_重构报告.md"
  "软件构造/实验5_开源复用与WASM方案.md"
  "软件构造/软件构造_实验1_报告.docx"
  "软件构造/软件构造-实验2.pptx"
  "软件构造/软件构造-实验3.pptx"
  "软件构造/软件构造-实验4.pptx"
  "软件构造/软件构造-实验5.pptx"
  "scripts/run_experiment2_design_validation.sh"
  "scripts/run_experiment3_tdd_validation.sh"
  "scripts/run_experiment4_refactor_validation.sh"
  "scripts/run_experiment5_reuse_validation.sh"
)

for file in "${REQUIRED_FILES[@]}"; do
  if [[ ! -f "${ROOT_DIR}/${file}" ]]; then
    echo "Missing required deliverable: ${file}" >&2
    exit 1
  fi
done
echo "Required deliverables are present."
echo

echo "== markdown and diagram content smoke =="
rg -n "baseline|不推倒重来|增量加速层|fallback" \
  "${ROOT_DIR}/软件构造/README.md" \
  "${ROOT_DIR}/软件构造/重构总体架构.md" >/dev/null
rg -n "Strategy|Adapter|Chain of Responsibility|Template Method" \
  "${ROOT_DIR}/软件构造/实验2_设计文档.md" \
  "${ROOT_DIR}/软件构造/实验2_类图.puml" >/dev/null
rg -n "TDD|audio_core|WASM|Django" \
  "${ROOT_DIR}/软件构造/实验3_TDD验证报告.md" >/dev/null
rg -n "重构|audio_core|Extract Module|Feature Flag" \
  "${ROOT_DIR}/软件构造/实验4_重构报告.md" >/dev/null
rg -n "libfvad|WebRTC VAD|Emscripten|WASM" \
  "${ROOT_DIR}/软件构造/实验5_开源复用与WASM方案.md" >/dev/null
echo "Document content smoke passed."
echo

echo "== validation scripts =="
bash -n "${ROOT_DIR}/scripts/run_experiment2_design_validation.sh"
bash -n "${ROOT_DIR}/scripts/run_experiment3_tdd_validation.sh"
bash -n "${ROOT_DIR}/scripts/run_experiment4_refactor_validation.sh"
bash -n "${ROOT_DIR}/scripts/run_experiment5_reuse_validation.sh"
"${ROOT_DIR}/scripts/run_experiment2_design_validation.sh"
"${ROOT_DIR}/scripts/run_experiment3_tdd_validation.sh"
"${ROOT_DIR}/scripts/run_experiment4_refactor_validation.sh"
"${ROOT_DIR}/scripts/run_experiment5_reuse_validation.sh"
python3 "${ROOT_DIR}/scripts/validate_legacy_server_retirement.py"
echo

echo "Software construction deliverables validation passed."
