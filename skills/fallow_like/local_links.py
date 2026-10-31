"""Bounded local Markdown target checks against a supplied repository inventory.

No filesystem, network or model access occurs. This is a single-line Markdown
subset, not a CommonMark renderer. Link anchors and remote URLs are not checked.
"""

from __future__ import annotations

from bisect import bisect_left
import html
import posixpath
import re
import string
from urllib.parse import unquote, urlsplit

_MAX_PATH_BYTES = 4096
_MAX_DOCUMENT_BYTES = 1024 * 1024
_MAX_TOTAL_BYTES = 8 * 1024 * 1024
_DETAILS = 50
_ESCAPES = re.compile(r"\\([" + re.escape(string.punctuation) + r"])")
_FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})(.*)$")
_DEFINITION = re.compile(r"^ {0,3}\[([^\]\n]+)\]:[ \t]*(.*)$")
_HTML_LINK = re.compile(r"<[^>\n]*\b(?:href|src)\s*=", re.I)
_HTML_TAG = re.compile(r"</?[A-Za-z][A-Za-z0-9:-]*(?:[ \t/>]|$)")
_RAW_HTML = re.compile(r"<\s*(script|style|pre|textarea)(?:[ \t/>]|$)", re.I)


def _utf8(value: str, label: str) -> int:
    try:
        return len(value.encode("utf-8"))
    except UnicodeEncodeError as exc:
        raise ValueError(f"{label} must contain valid Unicode") from exc


def _path(value, label):
    if not isinstance(value, str) or not value or _utf8(value, label) > _MAX_PATH_BYTES:
        raise ValueError(f"{label} must be a nonempty path of at most 4096 UTF-8 bytes")
    if (value.startswith("/") or "\\" in value or ":" in value or "\x00" in value
            or any(ord(c) < 32 or ord(c) == 127 for c in value)
            or any(part in ("", ".", "..") for part in value.split("/"))):
        raise ValueError(f"{label} must be a normalized repository-relative POSIX path")
    return value


def _unescape(value):
    return html.unescape(_ESCAPES.sub(r"\1", value))


def _label(value):
    return " ".join(_unescape(value).split()).casefold()


def _destination(line, start, *, definition=False):
    """Parse a single-line inline destination or a reference definition tail."""
    n, i = len(line), start
    while i < n and line[i] in " \t":
        i += 1
    if i >= n:
        return ("", i) if definition else None
    raw_start = i
    if line[i] == "<":
        i += 1
        raw_start = i
        while i < n:
            if line[i] == "\\" and i + 1 < n:
                i += 2
                continue
            if line[i] == ">":
                raw = line[raw_start:i]
                i += 1
                break
            if line[i] == "<":
                return None
            i += 1
        else:
            return None
    else:
        depth = 0
        while i < n:
            ch = line[i]
            if ch == "\\" and i + 1 < n and line[i + 1] in string.punctuation:
                i += 2
                continue
            if ch in " \t":
                break
            if ch == "(":
                depth += 1
                if depth > 32:
                    return None
            elif ch == ")":
                if depth == 0:
                    break
                depth -= 1
            if ch in "<>" or ord(ch) < 32:
                return None
            i += 1
        if depth:
            return None
        raw = line[raw_start:i]
    had_space = i < n and line[i] in " \t"
    while i < n and line[i] in " \t":
        i += 1
    if had_space and i < n and line[i] in "\"'(":
        delimiter = ")" if line[i] == "(" else line[i]
        i += 1
        while i < n:
            if line[i] == "\\" and i + 1 < n:
                i += 2
            elif line[i] == delimiter:
                i += 1
                break
            else:
                i += 1
        else:
            return None
        while i < n and line[i] in " \t":
            i += 1
    if definition:
        return (_unescape(raw), i) if i == n else None
    return (_unescape(raw), i + 1) if i < n and line[i] == ")" else None


def _masked_lines(text):
    """Mask code/comments in one pass, keeping offsets and line numbers.

    Backtick-run partners are indexed once, avoiding repeated suffix searches on
    documents containing many unmatched runs. Unsupported container contexts are
    skipped with a coverage issue rather than guessed as ordinary paragraphs.
    """
    runs = list(re.finditer(r"`+", text))
    partners, following = {}, {}
    for match in reversed(runs):
        length = match.end() - match.start()
        if length in following:
            partners[match.start()] = following[length]
        following[length] = match.end()
    comment, fence, code_end, offset, html_block = False, None, 0, 0, False
    for number, original in enumerate(text.splitlines(keepends=True), 1):
        content = original.rstrip("\r\n")
        issues = []
        if html_block:
            if html_block == "unterminated-inline-tag":
                pass
            elif isinstance(html_block, str):
                if re.search(r"</\s*" + html_block + r"\s*>", content, re.I):
                    html_block = False
            elif not content.strip():
                html_block = False
            yield number, content, "", issues
            offset += len(original)
            continue
        if fence:
            marker = _FENCE.match(content)
            if (marker and marker.group(1)[0] == fence[0]
                    and len(marker.group(1)) >= fence[1] and not marker.group(2).strip()):
                fence = None
            yield number, content, "", issues
            offset += len(original)
            continue
        if not comment and code_end <= offset:
            if content.lstrip().startswith(">"):
                if "[" in content or _HTML_LINK.search(content):
                    issues.append("blockquote_context_not_checked")
                yield number, content, "", issues
                offset += len(original)
                continue
            if content.startswith("    ") or content.startswith("\t"):
                if "[" in content or _HTML_LINK.search(content):
                    issues.append("indented_context_not_checked")
                yield number, content, "", issues
                offset += len(original)
                continue
            if re.match(r"^ {0,3}</?[A-Za-z][A-Za-z0-9:-]*(?:[ \t/>]|$)", content):
                raw = _RAW_HTML.search(content)
                html_block = raw.group(1).casefold() if raw else True
                if raw and re.search(r"</\s*" + raw.group(1) + r"\s*>", content[raw.end():], re.I):
                    html_block = False
                issues.append("html_block_not_checked")
                yield number, content, "", issues
                offset += len(original)
                continue
            marker = _FENCE.match(content)
            if marker and not (marker.group(1)[0] == "`" and "`" in marker.group(2)):
                fence = marker.group(1)[0], len(marker.group(1))
                yield number, content, "", issues
                offset += len(original)
                continue
        line, i = list(content), 0
        while i < len(line):
            absolute = offset + i
            if absolute < code_end:
                stop = min(len(line), code_end - offset)
                line[i:stop] = " " * (stop - i)
                i = stop
            elif comment:
                end = content.find("-->", i)
                stop = len(line) if end < 0 else end + 3
                line[i:stop] = " " * (stop - i)
                i = stop
                comment = end < 0
            elif content.startswith("<!--", i):
                comment = True
            elif content[i] == "\\" and i + 1 < len(line):
                i += 2
            elif content[i] == "`":
                end = i + 1
                while end < len(line) and content[end] == "`":
                    end += 1
                if absolute in partners:
                    code_end = partners[absolute]
                    if code_end > offset + len(content):
                        issues.append("multiline_code_span_not_checked")
                else:
                    i = end
            else:
                i += 1
        visible = "".join(line)
        for tag in _HTML_TAG.finditer(visible):
            quote = None
            closed = False
            for character in visible[tag.start():]:
                if quote:
                    if character == quote:
                        quote = None
                elif character in "\"'":
                    quote = character
                elif character == ">":
                    closed = True
                    break
            if not closed:
                # An unterminated inline tag may continue with attribute text
                # containing Markdown-looking brackets on subsequent lines.
                # This subset cannot establish its end, so conservatively omit
                # the remaining document and retain partial-coverage evidence.
                html_block = "unterminated-inline-tag"
                issues.append("multiline_html_tag_not_checked")
                visible = ""
                break
        raw = _RAW_HTML.search(visible)
        if raw:
            html_block = raw.group(1).casefold()
            if re.search(r"</\s*" + html_block + r"\s*>", visible[raw.end():], re.I):
                html_block = False
            issues.append("html_block_not_checked")
            visible = ""
        yield number, content, visible, issues
        offset += len(original)


def extract_markdown_links(text: str, *, max_links: int = 10000) -> dict:
    """Extract the documented single-line subset with explicit coverage issues.

    Handles inline links/images and single-line reference definitions (explicit,
    collapsed and shortcut uses). Fences, inline code, comments and indented code
    are excluded. HTML href/src and multiline link syntax are not supported.
    """
    if not isinstance(text, str) or _utf8(text, "text") > _MAX_DOCUMENT_BYTES:
        raise ValueError("text must be a string of at most 1 MiB UTF-8")
    if isinstance(max_links, bool) or not isinstance(max_links, int) or not 1 <= max_links <= 50000:
        raise ValueError("max_links must be an integer from 1 through 50000")
    lines = list(_masked_lines(text))
    definitions, definition_lines = {}, set()
    issues, issue_count = [], 0

    def issue(line, reason):
        nonlocal issue_count
        issue_count += 1
        if len(issues) < _DETAILS:
            issues.append({"line": line, "reason": reason})

    for number, original, visible, context_issues in lines:
        match = _DEFINITION.match(visible)
        if match:
            definition_lines.add(number)
            destination = _destination(original, match.start(2), definition=True)
            if destination is None or not destination[0]:
                issue(number, "unsupported_reference_definition")
            else:
                definitions.setdefault(_label(match.group(1)), destination[0])
    links, truncated = [], False
    for number, original, visible, context_issues in lines:
        for reason in context_issues:
            issue(number, reason)
        if not visible or number in definition_lines:
            continue
        # An angle-bracket destination is link syntax rather than an HTML tag.
        html_view = re.sub(r"\]\([ \t]*<[^>]*>", "", visible)
        if _HTML_TAG.search(html_view):
            issue(number, "html_link_not_checked")
            continue
        stack, pairs, parents, escaped = [], {}, {}, False
        too_deep = False
        for i, ch in enumerate(visible):
            if escaped:
                escaped = False
                continue
            if ch == "\\":
                escaped = True
            elif ch == "[":
                parents[i] = stack[-1] if stack else None
                stack.append(i)
                if len(stack) > 32:
                    too_deep = True
                    break
            elif ch == "]" and stack:
                pairs[stack.pop()] = i
        if too_deep:
            issue(number, "bracket_nesting_not_checked")
            continue
        if stack and number < len(lines) and "](" in lines[number][2]:
            issue(number, "multiline_link_not_checked")
        if (pairs and number < len(lines)
                and lines[number][2].lstrip().startswith("(")):
            issue(number, "multiline_link_not_checked")
        consumed = bytearray(len(visible))
        parsed_starts, line_links = set(), []
        nested_link = False
        for start in sorted(pairs):
            if consumed[start]:
                continue
            close = pairs[start]
            after = close + 1
            target, kind = None, "inline"
            if after < len(visible) and visible[after] == "(":
                destination = _destination(original, after + 1)
                if destination is None:
                    issue(number, "unsupported_inline_link")
                    continue
                target, end = destination
                # Ignore bracket syntax occurring inside the destination/title.
                consumed[after:end] = b"\1" * (end - after)
            elif after < len(visible) and visible[after] == "[" and after in pairs:
                ref_close = pairs[after]
                label = original[after + 1:ref_close] or original[start + 1:close]
                target = definitions.get(_label(label))
                consumed[after:ref_close + 1] = b"\1" * (ref_close + 1 - after)
                kind = "reference"
                if target is None:
                    # Undefined references are literal text in Markdown.
                    continue
            else:
                target = definitions.get(_label(original[start + 1:close]))
                kind = "reference"
                if target is None:
                    continue
            ancestor = parents.get(start)
            while ancestor is not None and ancestor not in parsed_starts:
                ancestor = parents.get(ancestor)
            if ancestor is not None and not (start > 0 and visible[start - 1] == "!"):
                nested_link = True
                break
            parsed_starts.add(start)
            if _utf8(target, "link target") > _MAX_PATH_BYTES:
                issue(number, "link_target_too_long")
                continue
            line_links.append({"line": number, "target": target, "kind": kind})
        if nested_link:
            issue(number, "nested_link_context_not_checked")
            continue
        for link in line_links:
            if len(links) >= max_links:
                truncated = True
                break
            links.append(link)
        if truncated:
            break
    return {"links": links, "issues": issues, "issues_omitted": issue_count - len(issues),
            "issue_count": issue_count, "truncated": truncated}


def _resolve(source, target):
    if not target or target.startswith("#"):
        return "anchor_only", None, "anchor_not_checked"
    if target.startswith("//"):
        return "external", None, "remote_not_checked"
    if re.match(r"^[A-Za-z]:", target) or "\\" in target:
        return "unsupported", None, "non_posix_target"
    try:
        parsed = urlsplit(target)
        if parsed.scheme:
            return "external", None, "remote_not_checked"
        decoded = unquote(parsed.path, errors="strict")
    except (ValueError, UnicodeDecodeError):
        return "unsupported", None, "invalid_url_target"
    if not decoded:
        return "anchor_only", None, "anchor_not_checked"
    if (decoded.startswith("/") or "\\" in decoded or ":" in decoded
            or any(ord(c) < 32 or ord(c) == 127 for c in decoded)):
        return "outside_root", None, "absolute_or_non_posix_target"
    resolved = posixpath.normpath(posixpath.join(posixpath.dirname(source), decoded))
    if resolved == ".." or resolved.startswith("../"):
        return "outside_root", None, "target_outside_inventory_root"
    return "local", resolved, None


def check_local_links(documents: list[dict], available_paths: list[str], *,
                      inventory_complete: bool = False, max_links: int = 10000) -> dict:
    """Check supplied Markdown against supplied paths; never inspect a live tree.

    Missing entries are definitive only relative to an explicitly declared
    complete inventory. Incomplete inventories always produce partial coverage.
    """
    if not isinstance(inventory_complete, bool):
        raise ValueError("inventory_complete must be a boolean")
    if isinstance(max_links, bool) or not isinstance(max_links, int) or not 1 <= max_links <= 50000:
        raise ValueError("max_links must be an integer from 1 through 50000")
    if not isinstance(documents, list) or not 1 <= len(documents) <= 200:
        raise ValueError("documents must contain from 1 through 200 objects")
    if not isinstance(available_paths, list) or len(available_paths) > 50000:
        raise ValueError("available_paths must be a list of at most 50000 paths")
    inventory, total_inventory = set(), 0
    for path in available_paths:
        path = _path(path, "inventory path")
        if path in inventory:
            raise ValueError("available_paths must contain unique paths")
        inventory.add(path)
        total_inventory += _utf8(path, "inventory path")
        if total_inventory > _MAX_TOTAL_BYTES:
            raise ValueError("inventory paths exceed 8 MiB UTF-8")
    sources, total_documents = {}, 0
    for document in documents:
        if not isinstance(document, dict) or set(document) != {"path", "text"}:
            raise ValueError("each document must contain exactly path and text")
        path = _path(document["path"], "document path")
        if not path.casefold().endswith(".md"):
            raise ValueError("document paths must have a .md extension")
        if path in sources:
            raise ValueError("document paths must be unique")
        text = document["text"]
        if not isinstance(text, str) or _utf8(text, "document text") > _MAX_DOCUMENT_BYTES:
            raise ValueError("each document text must be at most 1 MiB UTF-8")
        total_documents += _utf8(text, "document text")
        if total_documents > _MAX_TOTAL_BYTES:
            raise ValueError("document texts exceed 8 MiB UTF-8")
        sources[path] = text
    # Supplied documents are themselves known paths, even if not repeated in the
    # inventory. Parent directories are known from either supplied collection.
    known = inventory | set(sources)
    sorted_known = sorted(known)

    def listed(path):
        if path == "." or path in known:
            return True
        # Infer directories without materializing potentially millions of
        # intermediate path prefixes from a deeply nested supplied inventory.
        prefix = path + "/"
        position = bisect_left(sorted_known, prefix)
        return position < len(sorted_known) and sorted_known[position].startswith(prefix)

    counts = {key: 0 for key in ("links_examined", "present", "missing", "unresolved",
                                 "external", "anchor_only", "outside_root", "unsupported")}
    counts.update(documents=len(sources), inventory_paths=len(inventory))
    findings, finding_count, reasons = [], 0, set()
    if not inventory_complete:
        reasons.add("inventory_incomplete")

    def finding(path, line, target, resolved, status, reason):
        nonlocal finding_count
        finding_count += 1
        if len(findings) < _DETAILS:
            findings.append({"path": path, "line": line, "target": target,
                             "resolved_path": resolved, "status": status, "reason": reason})

    remaining = max_links
    sorted_sources = sorted(sources)
    for index, path in enumerate(sorted_sources):
        if remaining == 0:
            # Later documents have not been parsed; never claim full coverage
            # merely because the examined prefix exactly consumed the budget.
            if index < len(sorted_sources):
                reasons.add("max_links")
            break
        extracted = extract_markdown_links(sources[path], max_links=remaining)
        if extracted["truncated"]:
            reasons.add("max_links")
        if extracted["issue_count"]:
            reasons.add("unsupported_markdown")
            counts["unsupported"] += extracted["issue_count"]
            for issue in extracted["issues"]:
                finding(path, issue["line"], None, None, "unsupported", issue["reason"])
            finding_count += extracted["issues_omitted"]
        for link in extracted["links"]:
            counts["links_examined"] += 1
            remaining -= 1
            target = link["target"]
            status, resolved, reason = _resolve(path, target)
            if status == "local":
                status = "present" if listed(resolved) else "missing" if inventory_complete else "unresolved"
                reason = {"present": "present_in_supplied_data", "missing": "absent_from_supplied_complete_inventory",
                          "unresolved": "absent_from_supplied_partial_inventory"}[status]
            counts[status] += 1
            if status in ("outside_root", "unsupported"):
                reasons.add(reason)
            if status in ("missing", "unresolved", "outside_root", "unsupported"):
                finding(path, link["line"], target, resolved, status, reason)
        if extracted["truncated"]:
            break
    omitted = finding_count - len(findings)
    partial = bool(reasons)
    return {"schema": "parcimonia.local-links/v1", "status": "partial" if partial or omitted else "complete",
            "inventory_complete": inventory_complete, "counts": counts,
            "findings": findings, "findings_omitted": omitted,
            "coverage": {"partial": partial, "reasons": sorted(reasons)},
            "report_truncated": bool(omitted),
            "methods": {"syntax": "single_line_markdown_subset", "path_case": "sensitive",
                        "percent_decoding": "UTF-8", "anchors": "not_checked",
                        "evidence": "caller_supplied_documents_and_inventory"},
            "boundaries": {"filesystem": False, "network": False, "model_calls": 0}}
