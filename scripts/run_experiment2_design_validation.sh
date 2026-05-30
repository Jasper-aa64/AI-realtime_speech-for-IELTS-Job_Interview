#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DESIGN_DOC="${ROOT_DIR}/软件构造/实验2_设计文档.md"
CLASS_DIAGRAM="${ROOT_DIR}/软件构造/实验2_类图.puml"
ARCH_DOC="${ROOT_DIR}/软件构造/重构总体架构.md"

echo "== Experiment 2 design validation =="
echo "Repository: ${ROOT_DIR}"
echo

echo "== document presence =="
test -f "${DESIGN_DOC}"
test -f "${CLASS_DIAGRAM}"
test -f "${ARCH_DOC}"
echo "Design documents are present."
echo

echo "== baseline and scope guardrails =="
rg -n "baseline|不推倒重来|不改产品设计|保留现有成熟浏览器产品" \
  "${DESIGN_DOC}" "${ARCH_DOC}" >/dev/null
rg -n "Python 侧：.*AIProvider|C\\+\\+ 侧：.*接口与类图|不动现有 C\\+\\+ 实现" \
  "${DESIGN_DOC}" >/dev/null
echo "Baseline and experiment scope guardrails passed."
echo

echo "== four design patterns =="
for pattern in "Strategy" "Adapter" "Chain of Responsibility" "Template Method"; do
  rg -n "${pattern}" "${DESIGN_DOC}" "${CLASS_DIAGRAM}" >/dev/null
done
echo "Four required patterns are documented."
echo

echo "== Python-side design symbols =="
for symbol in \
  "AIProvider" \
  "AiTaskTemplate" \
  "HttpApiProvider" \
  "CodexProvider" \
  "ProviderChain" \
  "ProviderRunResult" \
  "FallbackProvider"; do
  rg -n "${symbol}" "${DESIGN_DOC}" "${CLASS_DIAGRAM}" >/dev/null
done
echo "Python-side AI provider design symbols passed."
echo

echo "== C++ realtime/audio design symbols =="
for symbol in \
  "AudioProcessor" \
  "ASRProvider" \
  "RealtimeGateway" \
  "ProtocolAdapter" \
  "FallbackPipeline" \
  "ScorerBackend"; do
  rg -n "${symbol}" "${DESIGN_DOC}" "${CLASS_DIAGRAM}" >/dev/null
done
echo "C++ realtime/audio interface design symbols passed."
echo

echo "== PlantUML structure =="
START_COUNT="$(rg '^@startuml' "${CLASS_DIAGRAM}" | wc -l | tr -d ' ')"
END_COUNT="$(rg '^@enduml' "${CLASS_DIAGRAM}" | wc -l | tr -d ' ')"
if [[ "${START_COUNT}" -ne 3 || "${END_COUNT}" -ne 3 ]]; then
  echo "Expected exactly 3 PlantUML diagrams, got start=${START_COUNT}, end=${END_COUNT}." >&2
  exit 1
fi
echo "PlantUML structure passed."
echo

echo "== implemented AI provider refactor smoke =="
rg -n "class AIProvider|class AiTaskTemplate|class ProviderChain|class HttpApiProvider|class CodexProvider" \
  "${ROOT_DIR}/backend_django/apps/ai/provider_adapters.py" >/dev/null
"${ROOT_DIR}/.venv-django/bin/python" "${ROOT_DIR}/backend_django/manage.py" test apps.ai -v 1
echo

echo "Experiment 2 design validation passed."
