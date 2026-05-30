(function () {
  "use strict";

  function escapeHtml(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#39;");
  }

  function escapeCssValue(value) {
    if (window.CSS?.escape) return window.CSS.escape(String(value ?? ""));
    return String(value ?? "").replace(/["\\]/g, "\\$&");
  }

  function renderMarkdown(value) {
    if (!value) return "";
    const codeSpans = [];
    let text = escapeHtml(value).replace(/\r\n/g, "\n").replace(/\r/g, "\n");
    text = text.replace(/`([^`\n]+?)`/g, (_match, code) => {
      const token = `@@CODE_SPAN_${codeSpans.length}@@`;
      codeSpans.push(`<code>${code}</code>`);
      return token;
    });
    text = text
      .replace(/\*\*([^*\n]+?)\*\*/g, "<strong>$1</strong>")
      .replace(/(^|[^\*])\*([^*\n]+?)\*/g, "$1<em>$2</em>");
    codeSpans.forEach((code, index) => {
      text = text.replaceAll(`@@CODE_SPAN_${index}@@`, code);
    });

    const lines = text.split("\n");
    const chunks = [];
    let i = 0;
    while (i < lines.length) {
      const line = lines[i].trim();
      if (!line) {
        i += 1;
        continue;
      }
      if (/^#{2,4}\s+/.test(line)) {
        chunks.push(`<h4>${line.replace(/^#{2,4}\s+/, "")}</h4>`);
        i += 1;
        continue;
      }
      if (/^[-*]\s+/.test(line)) {
        const items = [];
        while (i < lines.length && /^[-*]\s+/.test(lines[i].trim())) {
          const item = lines[i].trim().replace(/^[-*]\s+/, "");
          i += 1;
          const nested = [];
          while (i < lines.length && /^\s{2,}\d+\.\s+/.test(lines[i])) {
            nested.push(lines[i].trim().replace(/^\d+\.\s+/, ""));
            i += 1;
          }
          items.push(nested.length
            ? `${item}<ol>${nested.map((nestedItem) => `<li>${nestedItem}</li>`).join("")}</ol>`
            : item);
        }
        chunks.push(`<ul>${items.map((item) => `<li>${item}</li>`).join("")}</ul>`);
        continue;
      }
      if (/^\d+\.\s+/.test(line)) {
        const items = [];
        while (i < lines.length && /^\d+\.\s+/.test(lines[i].trim())) {
          items.push(lines[i].trim().replace(/^\d+\.\s+/, ""));
          i += 1;
        }
        chunks.push(`<ol>${items.map((item) => `<li>${item}</li>`).join("")}</ol>`);
        continue;
      }

      const paragraph = [];
      while (i < lines.length) {
        const current = lines[i].trim();
        if (!current || /^[-*]\s+/.test(current) || /^\d+\.\s+/.test(current) || /^#{2,4}\s+/.test(current)) break;
        paragraph.push(current);
        i += 1;
      }
      if (paragraph.length) chunks.push(`<p>${paragraph.join("<br>")}</p>`);
    }

    return chunks.join("");
  }

  function normalizeSpokenAnswerMarkdown(value) {
    if (!value) return "";
    const lines = String(value).replace(/\r\n/g, "\n").replace(/\r/g, "\n").split("\n");
    const normalized = [];
    let paragraph = [];
    let activeList = null;
    const proseJoin = (parts) => parts.join(" ")
      .replace(/(^|\s)\*\*\s+([^*]+?)\s+\*\*(?=\s|[,.;:!?]|$)/g, "$1**$2**")
      .replace(/(^|\s)\*\*\s+([^*]+?)\*\*(?=\s|[,.;:!?]|$)/g, "$1**$2**")
      .replace(/(^|\s)\*\*([^*]+?)\s+\*\*(?=\s|[,.;:!?]|$)/g, "$1**$2**")
      .replace(/\s+([,.;:!?])/g, "$1")
      .replace(/([([{])\s+/g, "$1")
      .replace(/\s+([)\]}])/g, "$1")
      .replace(/\s{2,}/g, " ")
      .trim();
    const flushParagraph = () => {
      if (!paragraph.length) return;
      const text = proseJoin(paragraph);
      if (text) normalized.push(text);
      paragraph = [];
    };
    const flushList = () => {
      if (!activeList) return;
      activeList.items.forEach((itemParts, index) => {
        const text = proseJoin(itemParts);
        if (!text) return;
        normalized.push(`${activeList.ordered ? `${index + 1}.` : "-"} ${text}`);
      });
      activeList = null;
    };
    const appendListItem = (ordered, text) => {
      if (!activeList || activeList.ordered !== ordered) {
        flushList();
        activeList = { ordered, items: [] };
      }
      activeList.items.push([text]);
    };

    lines.forEach((rawLine) => {
      const line = rawLine.trim();
      if (!line) {
        flushList();
        flushParagraph();
        if (normalized.length && normalized[normalized.length - 1] !== "") normalized.push("");
        return;
      }
      const bulletMatch = line.match(/^[-*]\s+(.+)$/);
      if (bulletMatch) {
        flushParagraph();
        appendListItem(false, bulletMatch[1]);
        return;
      }
      const orderedMatch = line.match(/^\d+\.\s+(.+)$/);
      if (orderedMatch) {
        flushParagraph();
        appendListItem(true, orderedMatch[1]);
        return;
      }
      if (/^(#{2,4}\s+|>\s+)/.test(line)) {
        flushList();
        flushParagraph();
        normalized.push(line);
        return;
      }
      if (activeList) {
        activeList.items[activeList.items.length - 1].push(line);
        return;
      }
      paragraph.push(line);
    });
    flushList();
    flushParagraph();
    return normalized.join("\n").replace(/\n{3,}/g, "\n\n").trim();
  }

  function renderSpokenAnswerMarkdown(value) {
    return renderMarkdown(normalizeSpokenAnswerMarkdown(value));
  }

  window.IELTSSharedUI = {
    escapeCssValue,
    escapeHtml,
    normalizeSpokenAnswerMarkdown,
    renderMarkdown,
    renderSpokenAnswerMarkdown,
  };
})();
