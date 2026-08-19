#!/usr/bin/env python3
"""
Granular AST Quality Engine
Evaluates Python source files against modular, configuration-driven static analysis rules.
"""

from typing import Any, Dict, List
from pathlib import Path
import yaml, json
import ast
import sys


class GranularASTVisitor(ast.NodeVisitor):
    def __init__(self, file_path: Path, config: Dict[str, Any]):
        self.file_path = file_path
        self.config = config
        self.violations: List[Dict[str, Any]] = []

    # --------------------------------------------------------------------------
    # IMPORTS & ARCHITECTURE CHECKS
    # --------------------------------------------------------------------------

    def _calculate_complexity(self, node: ast.AST) -> int:
        """Calculates Cyclomatic Complexity of a function AST node."""
        complexity = 1  # Base complexity for any function

        # AST nodes that introduce new execution paths
        branch_nodes = (
            ast.If,
            ast.For,
            ast.While,
            ast.ExceptHandler,
            ast.With,
            ast.Assert,
        )

        for child in ast.walk(node):
            # 1. Branching control statements
            if isinstance(child, branch_nodes):
                complexity += 1

            # 2. Boolean operators (e.g., `if a and b:` adds 2 decision paths)
            elif isinstance(child, ast.BoolOp):
                complexity += len(child.values) - 1

            # 3. Comprehensions with filtering `if` conditions
            elif isinstance(
                child, (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)
            ):
                for gen in child.generators:
                    complexity += len(gen.ifs)

        return complexity

    def visit_Import(self, node: ast.Import):
        self._check_forbidden_imports([alias.name for alias in node.names], node.lineno)
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom):
        file_cfg = self.config.get("file_rules", {})
        
        # Rule: No wildcard imports (from x import *)
        if file_cfg.get("no_wildcard_imports", {}).get("enabled", False):
            for alias in node.names:
                if alias.name == "*":
                    self.violations.append({
                        "rule": "NO_WILDCARD_IMPORT",
                        "severity": file_cfg["no_wildcard_imports"].get("severity", "HIGH"),
                        "target": f"Import from '{node.module}'",
                        "line": node.lineno,
                        "message": f"Wildcard import 'from {node.module} import *' pollutes namespace"
                    })

        if node.module:
            self._check_forbidden_imports([node.module], node.lineno)

        self.generic_visit(node)

    def _check_forbidden_imports(self, modules: List[str], line_no: int):
        arch_cfg = self.config.get("architectural_rules", {})
        rule_cfg = arch_cfg.get("disallowed_imports", {})
        if rule_cfg.get("enabled", False):
            forbidden = set(rule_cfg.get("modules", []))
            for mod in modules:
                if any(mod == f or mod.startswith(f + ".") for f in forbidden):
                    self.violations.append({
                        "rule": "DISALLOWED_IMPORT",
                        "severity": rule_cfg.get("severity", "CRITICAL"),
                        "target": f"Import '{mod}'",
                        "line": line_no,
                        "message": f"Importing '{mod}' is forbidden by architectural rules"
                    })

    # --------------------------------------------------------------------------
    # FUNCTION / METHOD CHECKS
    # --------------------------------------------------------------------------
    def visit_FunctionDef(self, node: ast.FunctionDef):
        self._check_function(node)
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef):
        self._check_function(node)
        self.generic_visit(node)

    def _check_function(self, node):
        func_cfg = self.config.get("function_rules", {})

        # Rule: Max Lines
        if func_cfg.get("max_lines", {}).get("enabled", False):
            rule = func_cfg["max_lines"]
            start_line = node.lineno
            end_line = getattr(node, "end_lineno", start_line)
            length = end_line - start_line + 1
            if length > rule["threshold"]:
                self.violations.append({
                    "rule": "MAX_FUNCTION_LINES",
                    "severity": rule.get("severity", "HIGH"),
                    "target": f"Function '{node.name}'",
                    "line": start_line,
                    "message": f"Function has {length} lines (max allowed: {rule['threshold']})"
                })

        # Rule: Max Arguments
        if func_cfg.get("max_arguments", {}).get("enabled", False):
            rule = func_cfg["max_arguments"]
            total_args = len(node.args.args) + len(node.args.kwonlyargs)
            if total_args > rule["threshold"]:
                self.violations.append({
                    "rule": "MAX_FUNCTION_ARGS",
                    "severity": rule.get("severity", "MEDIUM"),
                    "target": f"Function '{node.name}'",
                    "line": node.lineno,
                    "message": f"Function has {total_args} parameters (max allowed: {rule['threshold']})"
                })

        # Rule: Type Hints Required (Parameters & Return)
        if func_cfg.get("require_type_hints", {}).get("enabled", False):
            rule = func_cfg["require_type_hints"]
            missing_hints = []
            for arg in node.args.args:
                if arg.arg != "self" and arg.arg != "cls" and arg.annotation is None:
                    missing_hints.append(arg.arg)

            if missing_hints or node.returns is None:
                details = []
                if missing_hints:
                    details.append(f"missing arg types: {', '.join(missing_hints)}")
                if node.returns is None:
                    details.append("missing return type")
                
                self.violations.append({
                    "rule": "MISSING_TYPE_HINTS",
                    "severity": rule.get("severity", "LOW"),
                    "target": f"Function '{node.name}'",
                    "line": node.lineno,
                    "message": f"Function '{node.name}' lacks type annotations ({'; '.join(details)})"
                })

        # Rule: Max Return Statements
        if func_cfg.get("max_returns", {}).get("enabled", False):
            rule = func_cfg["max_returns"]
            returns_count = sum(1 for child in ast.walk(node) if isinstance(child, ast.Return))
            if returns_count > rule["threshold"]:
                self.violations.append({
                    "rule": "MAX_RETURN_STATEMENTS",
                    "severity": rule.get("severity", "MEDIUM"),
                    "target": f"Function '{node.name}'",
                    "line": node.lineno,
                    "message": f"Function has {returns_count} return statements (max allowed: {rule['threshold']})"
                })

        # Rule: Max Nesting Depth
        if func_cfg.get("max_nesting_depth", {}).get("enabled", False):
            rule = func_cfg["max_nesting_depth"]
            max_depth = self._calculate_max_nesting(node)
            if max_depth > rule["threshold"]:
                self.violations.append({
                    "rule": "MAX_NESTING_DEPTH",
                    "severity": rule.get("severity", "HIGH"),
                    "target": f"Function '{node.name}'",
                    "line": node.lineno,
                    "message": f"Nesting depth is {max_depth} (max allowed: {rule['threshold']})"
                })

        # Rule: Cyclomatic Complexity
        if func_cfg.get("max_cyclomatic_complexity", {}).get("enabled", False):
            rule = func_cfg["max_cyclomatic_complexity"]
            complexity = self._calculate_complexity(node)

            if complexity > rule["threshold"]:
                self.violations.append(
                    {
                        "rule": "HIGH_CYCLOMATIC_COMPLEXITY",
                        "severity": rule.get("severity", "HIGH"),
                        "target": f"Function '{node.name}'",
                        "line": node.lineno,
                        "message": (
                            f"Function '{node.name}' has a cyclomatic complexity of {complexity} "
                            f"(max allowed: {rule['threshold']}). Consider refactoring into smaller helper functions."
                        ),
                    }
                )

        if func_cfg.get("no_mutable_defaults", {}).get("enabled", False):
            rule = func_cfg["no_mutable_defaults"]

            # Combine positional defaults and keyword-only defaults
            all_defaults = node.args.defaults + node.args.kw_defaults

            for default in all_defaults:
                if default is None:
                    continue

                # 1. Direct mutable literals: [], {}, {1, 2}
                is_mutable_literal = isinstance(
                    default, (ast.List, ast.Dict, ast.Set)
                )

                # 2. Constructor calls: list(), dict(), set()
                is_mutable_call = (
                    isinstance(default, ast.Call)
                    and isinstance(default.func, ast.Name)
                    and default.func.id in {"list", "dict", "set"}
                )

                if is_mutable_literal or is_mutable_call:
                    self.violations.append(
                        {
                            "rule": "MUTABLE_DEFAULT_ARGUMENT",
                            "severity": rule.get("severity", "HIGH"),
                            "target": f"Function '{node.name}'",
                            "line": default.lineno,
                            "message": (
                                f"Function '{node.name}' uses a mutable default argument. "
                                "Default mutable objects persist across function calls! "
                                "Use 'None' as the default value and initialize inside the function body instead."
                            ),
                        }
                    )

    def _calculate_max_nesting(self, node: ast.AST, current_depth: int = 0) -> int:
        nested_blocks = (ast.If, ast.For, ast.While, ast.With, ast.Try)
        max_depth = current_depth

        for child in ast.iter_child_nodes(node):
            if isinstance(child, nested_blocks):
                child_depth = self._calculate_max_nesting(child, current_depth + 1)
            else:
                child_depth = self._calculate_max_nesting(child, current_depth)
            max_depth = max(max_depth, child_depth)

        return max_depth

    # --------------------------------------------------------------------------
    # CLASS CHECKS
    # --------------------------------------------------------------------------
    def visit_ClassDef(self, node: ast.ClassDef):
        class_cfg = self.config.get("class_rules", {})

        # Rule: Require Class Docstring
        if class_cfg.get("require_docstring", {}).get("enabled", False):
            rule = class_cfg["require_docstring"]
            if not ast.get_docstring(node):
                self.violations.append({
                    "rule": "MISSING_CLASS_DOCSTRING",
                    "severity": rule.get("severity", "LOW"),
                    "target": f"Class '{node.name}'",
                    "line": node.lineno,
                    "message": f"Class '{node.name}' is missing a docstring"
                })

        # Rule: Max Methods
        if class_cfg.get("max_methods", {}).get("enabled", False):
            rule = class_cfg["max_methods"]
            methods = [n for n in node.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
            if len(methods) > rule["threshold"]:
                self.violations.append({
                    "rule": "MAX_CLASS_METHODS",
                    "severity": rule.get("severity", "MEDIUM"),
                    "target": f"Class '{node.name}'",
                    "line": node.lineno,
                    "message": f"Class has {len(methods)} methods (max allowed: {rule['threshold']})"
                })

        self.generic_visit(node)

    # --------------------------------------------------------------------------
    # CODE SMELLS & CALL CHECKS
    # --------------------------------------------------------------------------
    def visit_ExceptHandler(self, node: ast.ExceptHandler):
        smell_cfg = self.config.get("code_smell_rules", {})

        # Rule: No Bare Except
        if smell_cfg.get("no_bare_except", {}).get("enabled", False):
            rule = smell_cfg["no_bare_except"]
            if node.type is None:
                self.violations.append({
                    "rule": "NO_BARE_EXCEPT",
                    "severity": rule.get("severity", "HIGH"),
                    "target": "Except Block",
                    "line": node.lineno,
                    "message": "Bare 'except:' caught. Always catch explicit Exception types"
                })

        self.generic_visit(node)

    def visit_Call(self, node: ast.Call):
        smell_cfg = self.config.get("code_smell_rules", {})

        # Rule: Disallowed Function Calls (eval, exec, breakpoint)
        if smell_cfg.get("disallowed_calls", {}).get("enabled", False):
            rule = smell_cfg["disallowed_calls"]
            forbidden_fns = set(rule.get("functions", []))

            if isinstance(node.func, ast.Name) and node.func.id in forbidden_fns:
                self.violations.append({
                    "rule": "DISALLOWED_FUNCTION_CALL",
                    "severity": rule.get("severity", "CRITICAL"),
                    "target": f"Call '{node.func.id}()'",
                    "line": node.lineno,
                    "message": f"Use of '{node.func.id}()' is prohibited"
                })

        # Rule: No print statements (force logging instead)
        if smell_cfg.get("no_print_statements", {}).get("enabled", False):
            rule = smell_cfg["no_print_statements"]
            if isinstance(node.func, ast.Name) and node.func.id == "print":
                self.violations.append({
                    "rule": "NO_PRINT_STATEMENT",
                    "severity": rule.get("severity", "LOW"),
                    "target": "print()",
                    "line": node.lineno,
                    "message": "Use structured logging instead of raw print() statements"
                })

        self.generic_visit(node)


def analyze_file(file_path: Path, config: Dict[str, Any]) -> List[Dict[str, Any]]:
    violations = []
    try:
        content = file_path.read_text(encoding="utf-8")
    except Exception as e:
        return [{
            "rule": "READ_ERROR",
            "severity": "HIGH",
            "target": str(file_path),
            "line": 0,
            "message": f"Could not read file: {e}"
        }]

    lines = content.splitlines()
    file_cfg = config.get("file_rules", {})

    # Rule: Max File Lines
    if file_cfg.get("max_lines", {}).get("enabled", False):
        rule = file_cfg["max_lines"]
        if len(lines) > rule["threshold"]:
            violations.append({
                "rule": "MAX_FILE_LINES",
                "severity": rule.get("severity", "HIGH"),
                "target": f"File '{file_path.name}'",
                "line": 1,
                "message": f"File has {len(lines)} lines (max allowed: {rule['threshold']})"
            })

    try:
        tree = ast.parse(content, filename=str(file_path))

        # Rule: Max Classes Per File
        if file_cfg.get("max_classes_per_file", {}).get("enabled", False):
            rule = file_cfg["max_classes_per_file"]
            classes_count = sum(1 for node in tree.body if isinstance(node, ast.ClassDef))
            if classes_count > rule["threshold"]:
                violations.append({
                    "rule": "MAX_CLASSES_PER_FILE",
                    "severity": rule.get("severity", "MEDIUM"),
                    "target": f"File '{file_path.name}'",
                    "line": 1,
                    "message": f"File contains {classes_count} classes (max allowed: {rule['threshold']})"
                })

        visitor = GranularASTVisitor(file_path, config)
        visitor.visit(tree)
        violations.extend(visitor.violations)

    except SyntaxError as err:
        violations.append({
            "rule": "SYNTAX_ERROR",
            "severity": "CRITICAL",
            "target": f"File '{file_path.name}'",
            "line": err.lineno or 1,
            "message": f"Syntax error: {err.msg}"
        })

    return violations


def run_engine(config_path: str = "scripts/quality_rules.yaml", target_dir: str = ".") -> Dict[str, Any]:
    cfg_file = Path(config_path)
    if not cfg_file.exists():
        print(f"❌ Config '{config_path}' not found!")
        sys.exit(1)

    config = yaml.safe_load(cfg_file.read_text(encoding="utf-8"))
    exclude_dirs = set(config.get("exclude_dirs", []))
    blocking_severities = set(
        config.get("gate_settings", {}).get("blocking_severities", ["CRITICAL", "HIGH", "MEDIUM"])
    )

    root = Path(target_dir)
    results = {
        "summary": {
            "files_scanned": 0,
            "total_violations": 0,
            "blocking_violations": 0,
            "status": "PASSED"
        },
        "files": []
    }

    for file_path in root.rglob("*.py"):
        if any(part in exclude_dirs for part in file_path.parts):
            continue

        results["summary"]["files_scanned"] += 1
        violations = analyze_file(file_path, config)

        if violations:
            results["summary"]["total_violations"] += len(violations)
            for v in violations:
                if v["severity"] in blocking_severities:
                    results["summary"]["blocking_violations"] += 1

            results["files"].append({
                "file": str(file_path.relative_to(root)),
                "violations": violations
            })

    if results["summary"]["blocking_violations"] > 0:
        results["summary"]["status"] = "FAILED"
    elif results["summary"]["total_violations"] > 0:
        results["summary"]["status"] = "PASSED_WITH_WARNINGS"

    return results


# def export_reports(data: Dict[str, Any]):
#     Path("quality_report.json").write_text(json.dumps(data, indent=2), encoding="utf-8")

#     status = data["summary"]["status"]
#     status_icon = "✅ PASSED" if status == "PASSED" else ("⚠️ PASSED (Warnings)" if status == "PASSED_WITH_WARNINGS" else "❌ FAILED")

#     md_lines = [
#         "### 📐 Granular Quality Engine Report",
#         "",
#         f"**Status:** {status_icon} | **Files Scanned:** `{data['summary']['files_scanned']}` | **Blocking Failures:** `{data['summary']['blocking_violations']}` | **Total Warnings:** `{data['summary']['total_violations']}`",
#         "",
#         "| File | Line | Rule | Severity | Details |",
#         "| :--- | :---: | :--- | :---: | :--- |"
#     ]

#     if not data["files"]:
#         md_lines.append("| _All files_ | — | _Clean Code_ | 🟢 INFO | All granular quality rules satisfied! |")
#     else:
#         severity_icons = {"CRITICAL": "🔴", "HIGH": "🟠", "MEDIUM": "🟡", "LOW": "🔵"}
#         for file_entry in data["files"]:
#             file_name = file_entry["file"]
#             for v in file_entry["violations"]:
#                 icon = severity_icons.get(v["severity"], "⚪")
#                 md_lines.append(
#                     f"| `{file_name}` | `{v['line']}` | `{v['rule']}` | {icon} {v['severity']} | {v['message']} |"
#                 )

#     md_lines.extend(["", "*Generated by `scripts/quality_engine.py`*"])
#     Path("quality_summary.md").write_text("\n".join(md_lines), encoding="utf-8")

def export_reports(data: Dict[str, Any]):
    # Save raw JSON audit artifact
    Path("quality_report.json").write_text(json.dumps(data, indent=2), encoding="utf-8")

    summary = data.get("summary", {})
    status = summary.get("status", "PASSED")
    
    # Calculate severity & rule distributions
    sev_counts = {"CRITICAL": 0, "HIGH": 0, "MEDIUM": 0, "LOW": 0}
    rule_counts: Dict[str, int] = {}
    
    for f in data.get("files", []):
        for v in f.get("violations", []):
            sev = v.get("severity", "LOW")
            sev_counts[sev] = sev_counts.get(sev, 0) + 1
            
            rule = v.get("rule", "UNKNOWN")
            rule_counts[rule] = rule_counts.get(rule, 0) + 1

    # Map status to enterprise badges
    status_badge = {
        "PASSED": "🟢 **PASSED (GATE SUCCESS)**",
        "PASSED_WITH_WARNINGS": "🟡 **PASSED WITH WARNINGS**",
        "FAILED": "🔴 **FAILED (GATE BLOCKED)**"
    }.get(status, "⚪ **UNKNOWN**")

    md = [
        "# 🛡️ Enterprise Static Analysis & Security Report",
        "---",
        "## 📌 Executive Summary",
        "",
        "| Metric | Result |",
        "| :--- | :--- |",
        f"| **Quality Gate Status** | {status_badge} |",
        f"| **Files Analyzed** | `{summary.get('files_scanned', 0)}` |",
        f"| **Total Violations** | `{summary.get('total_violations', 0)}` |",
        f"| **Blocking Violations** | `{summary.get('blocking_violations', 0)}` |",
        "",
        "### 📊 Violation Severity Matrix",
        "",
        "| 🔴 Critical | 🟠 High | 🟡 Medium | 🔵 Low |",
        "| :---: | :---: | :---: | :---: |",
        f"| **{sev_counts['CRITICAL']}** | **{sev_counts['HIGH']}** | **{sev_counts['MEDIUM']}** | **{sev_counts['LOW']}** |",
        ""
    ]

    # Rule Distribution Section
    if rule_counts:
        md.extend([
            "### 📈 Top Triggered Rules",
            "",
            "| Rule Identifier | Occurrences | Impact Level |",
            "| :--- | :---: | :---: |"
        ])
        sorted_rules = sorted(rule_counts.items(), key=lambda x: x[1], reverse=True)[:5]
        for rule_id, count in sorted_rules:
            md.append(f"| `{rule_id}` | `{count}` | Dynamic Policy |")
        md.append("")

    # Detailed Findings Section
    md.extend([
        "---",
        "## 🔍 Detailed Findings & Code Audit",
        ""
    ])

    if not data.get("files"):
        md.append("> ✅ **Clean Codebase**: Zero static security or quality violations detected across scanned targets.")
    else:
        severity_icons = {"CRITICAL": "🔴", "HIGH": "🟠", "MEDIUM": "🟡", "LOW": "🔵"}
        
        md.extend([
            "| Location | Rule | Severity | Message & Guidance |",
            "| :--- | :--- | :---: | :--- |"
        ])
        
        for file_entry in data["files"]:
            file_name = file_entry["file"]
            for v in file_entry["violations"]:
                icon = severity_icons.get(v["severity"], "⚪")
                location = f"`{file_name}:{v['line']}`"
                md.append(
                    f"| {location} | `{v['rule']}` | {icon} **{v['severity']}** | {v['message']} |"
                )

    # Compliance & CI/CD Gate Policy
    md.extend([
        "",
        "---",
        "## 🚨 Governance & Security Gate Policy",
        ""
    ])
    
    if status == "FAILED":
        md.append(
            "> ❌ **DEPLOYMENT BLOCKED**: The analysis identified blocking severity violations (`CRITICAL` / `HIGH`). "
            "PR merge is restricted until all policy-blocking items are resolved."
        )
    elif status == "PASSED_WITH_WARNINGS":
        md.append(
            "> ⚠️ **GATE PASSED WITH WARNINGS**: Non-blocking violations (`MEDIUM` / `LOW`) were detected. "
            "Addressing these items during the current sprint cycle is recommended."
        )
    else:
        md.append(
            "> ✅ **GATE PASSED**: All scanned targets comply with enterprise static analysis guidelines."
        )

    md.extend([
        "",
        "---",
        "*Automated report generated by **Granular AST Quality & SAST Engine**.*"
    ])

    Path("quality_summary.md").write_text("\n".join(md), encoding="utf-8")

if __name__ == "__main__":
    report_data = run_engine()
    export_reports(report_data)

    print(f"Analysis complete. Status: {report_data['summary']['status']}")
    print(f"Blocking violations: {report_data['summary']['blocking_violations']}")
    sys.exit(1 if report_data["summary"]["status"] == "FAILED" else 0)