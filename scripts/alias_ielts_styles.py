"""Share IELTS page styles with their mock-interview counterparts.

For every style rule whose selector names an IELTS page anchor (for example #p1CorpusPanel),
append an alias selector for the interview counterpart (#interviewCorpus) to the same rule.
(The interview home needs no alias: it is the IELTS #homePanel itself, see interview-home.js.)
The IELTS selectors are left untouched, and each alias swaps an id for an id (or a class for
a class), so specificity and cascade order are identical on both sides. Re-running is a no-op:
aliases already present are not added twice.

Usage: python3 scripts/alias_ielts_styles.py web/static/styles.css [--check]
"""

import re
import sys

# anchor -> (alias, extra rewrites applied only to the alias selector, alias page-level :has() rules too?)
ALIASES = [
    ("#p1CorpusPanel", "#interviewCorpus", [], True),
    ("#historyPanel", "#interviewReports", [], True),
    ("#historyList", "#interviewReportList", [], True),
    ("#detailPanel", "#interviewReportDetail", [], True),
    # Resume / JD page <-> daily writing.
    ("#writingPanel", "#interviewCustom", [], False),
    ("#writingScoreBtn", "#interviewCustomSubmit", [], False),
    ("#writingSaveBtn", "#interviewCustomCorpus", [], False),
]
# Speaking-report workspace conditions: shared for the rail/detail, never for writing reports.
HISTORY_WORKSPACE = (".history-workspace", ".interview-history-workspace")
SPEAKING_REPORT = re.compile(r"#historyPanel|#historyList|#detailPanel|\.history-rail|\.history-list|\.speaking-report")
WRITING = re.compile(r"writing", re.I)
# Corpus-view workspace conditions are shared only when the selector is about the P1 library.
CORPUS_WORKSPACE = (".corpus-workspace", ".interview-corpus-workspace")
P1_LIBRARY = re.compile(r"#p1CorpusPanel|\.p1-corpus-(?:shell|head|topics|dialog|label|textarea)|\.p1-topic-")
OTHER_PANELS = re.compile(r"#(?:corpusPanel|p2CorpusPanel|p2CorpusP3Dialog|languageTakeawayPanel|writingTakeawayPanel|spellingDrillPanel)")


def split_top_level(prelude):
    parts, depth, start, quote = [], 0, 0, ""
    for index, char in enumerate(prelude):
        if quote:
            if char == quote:
                quote = ""
            continue
        if char in "\"'":
            quote = char
        elif char in "([":
            depth += 1
        elif char in ")]":
            depth -= 1
        elif char == "," and depth == 0:
            parts.append(prelude[start:index])
            start = index + 1
    parts.append(prelude[start:])
    return parts


def outside_has(selector, token):
    """True when token appears in selector but not only inside :has(...) or :not(...).

    An alias inside :not() would invert the meaning: `x:not(#interviewPractice *)` added next to
    `x:not(#practicePanel *)` matches everything inside the IELTS panel again."""
    stripped = re.sub(r":(?:has|not)\((?:[^()]|\([^()]*\))*\)", "", selector)
    return token in stripped


def alias_for(selector):
    original = selector.strip()
    aliases = []
    for anchor, alias, rewrites, through_has in ALIASES:
        if anchor in original and (through_has or outside_has(original, anchor)):
            candidate = original.replace(anchor, alias)
            for pattern, replacement in rewrites:
                candidate = re.sub(pattern, replacement, candidate)
            candidate = candidate.replace(".workspace" + CORPUS_WORKSPACE[0], ".workspace" + CORPUS_WORKSPACE[1])
            candidate = candidate.replace(HISTORY_WORKSPACE[0], HISTORY_WORKSPACE[1])
            for other_anchor, other_alias, _rewrites, _has in ALIASES:
                candidate = candidate.replace(other_anchor, other_alias)
            if not WRITING.search(original) or anchor not in ("#historyPanel", "#historyList", "#detailPanel"):
                aliases.append(candidate)
            break
    if not aliases and CORPUS_WORKSPACE[0] in original and P1_LIBRARY.search(original) and not OTHER_PANELS.search(original):
        aliases.append(original.replace(CORPUS_WORKSPACE[0], CORPUS_WORKSPACE[1]))
    if not aliases and HISTORY_WORKSPACE[0] in original and SPEAKING_REPORT.search(original) and not WRITING.search(original):
        aliases.append(original.replace(HISTORY_WORKSPACE[0], HISTORY_WORKSPACE[1]))
    return [a for a in aliases if a != original]


def rewrite(css):
    out, i, n, changed = [], 0, len(css), 0
    prelude_start = 0
    depth_stack = []  # True for blocks whose children are rules (@media/@supports/@container)
    while i < n:
        if css.startswith("/*", i):
            end = css.find("*/", i + 2)
            i = n if end < 0 else end + 2
            continue
        char = css[i]
        if char in "\"'":
            end = i + 1
            while end < n and css[end] != char:
                end += 2 if css[end] == "\\" else 1
            i = end + 1
            continue
        if char == "{":
            prelude = css[prelude_start:i]
            body_is_rules = prelude.lstrip().startswith("@") and re.match(r"\s*@(media|supports|container|layer)", prelude)
            in_rule_context = not depth_stack or depth_stack[-1]
            if in_rule_context and not prelude.lstrip().startswith("@"):
                selectors = split_top_level(re.sub(r"/\*.*?\*/", "", prelude, flags=re.S))
                existing = {s.strip() for s in selectors}
                extra = []
                for selector in selectors:
                    for alias in alias_for(selector):
                        if alias not in existing and alias not in extra:
                            extra.append(alias)
                if extra:
                    trailing = prelude[len(prelude.rstrip()):]
                    prelude = prelude.rstrip() + ",\n" + ",\n".join(extra) + trailing
                    changed += 1
            out.append(prelude + "{")
            depth_stack.append(bool(body_is_rules))
            i += 1
            prelude_start = i
            continue
        if char == "}":
            out.append(css[prelude_start:i + 1])
            if depth_stack:
                depth_stack.pop()
            i += 1
            prelude_start = i
            continue
        if char == ";" and depth_stack and not depth_stack[-1]:
            pass
        i += 1
    out.append(css[prelude_start:])
    return "".join(out), changed


if __name__ == "__main__":
    path = sys.argv[1]
    source = open(path, encoding="utf-8").read()
    result, changed = rewrite(source)
    print(f"rules aliased: {changed}")
    if "--check" not in sys.argv:
        open(path, "w", encoding="utf-8").write(result)
