"""Code complexity analysis."""

from __future__ import annotations
from skills.fallow_like.scanner import ScanResult
from skills.fallow_like.models import ComplexityFinding, Severity
from tree_sitter import Node


class ComplexityAnalyzer:
    COMPLEXITY_NODES = {
        "if_statement", "elif_clause", "else_clause",
        "for_statement", "while_statement", "try_statement",
        "except_clause", "with_statement", "assert_statement",
        "conditional_expression",
        "switch_case", "catch_clause",
    }

    NESTING_TYPES = {
        "if_statement", "for_statement", "while_statement",
        "try_statement", "with_statement", "function_definition",
        "class_definition", "switch_statement",
    }

    def __init__(self, threshold: int = 10):
        self.threshold = threshold

    def analyze(self, scan: ScanResult) -> list:
        findings = []

        for file_ast in scan.files:
            for sym in file_ast.symbols:
                if sym.type != "function":
                    continue

                func_node = self._find_node_at_line(file_ast.tree.root_node, sym.line)
                if not func_node:
                    continue

                complexity = self._calc_cyclomatic(func_node)
                nesting = self._calc_max_nesting(func_node)
                loc = sym.end_line - sym.line + 1

                if complexity > self.threshold or nesting > 4:
                    severity = Severity.ERROR if complexity > 20 else Severity.WARNING
                    findings.append(ComplexityFinding(
                        rule_id="COMP001",
                        severity=severity,
                        message=(
                            f"Function '{sym.name}' has cyclomatic complexity {complexity} "
                            f"(threshold: {self.threshold}), nesting depth {nesting}"
                        ),
                        file=file_ast.path,
                        line=sym.line,
                        function_name=sym.name,
                        complexity=complexity,
                        nesting_depth=nesting,
                        lines_of_code=loc,
                        confidence=0.95,
                        fix_hint="Extract helper functions to reduce complexity",
                    ))

        return findings

    def _find_node_at_line(self, root: Node, line: int) -> Node | None:
        best = None
        if root.start_point[0] + 1 == line:
            best = root
        for child in root.children:
            found = self._find_node_at_line(child, line)
            if found and (best is None or
                          found.end_point[0] - found.start_point[0] <
                          best.end_point[0] - best.start_point[0]):
                best = found
        return best

    def _calc_cyclomatic(self, node: Node) -> int:
        count = 1
        if node.type in self.COMPLEXITY_NODES:
            count += 1
        for child in node.children:
            count += self._calc_cyclomatic(child) - 1
        return max(count, 1)

    def _calc_max_nesting(self, node: Node, depth: int = 0) -> int:
        new_depth = depth + 1 if node.type in self.NESTING_TYPES else depth
        max_depth = new_depth
        for child in node.children:
            child_depth = self._calc_max_nesting(child, new_depth)
            max_depth = max(max_depth, child_depth)
        return max_depth
