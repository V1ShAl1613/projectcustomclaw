#!/usr/bin/env python3
"""
Language Support Tools Module

Extends Hermes with enhanced language-specific analysis and tooling:
- Rust (cargo check, clippy, rustfmt, rust-analyzer)
- Python (mypy, pyright, ruff, black, pylint)
- TypeScript/JavaScript (tsc, eslint, prettier, biome)
- Go (go vet, staticcheck, golangci-lint, gofmt)
- Java (checkstyle, spotbugs, pmd, google-java-format)
- Kotlin (detekt, ktlint)
- Swift (swiftlint, swiftformat)
- C# (dotnet format, analyzers, roslynator)
- C++ (clang-tidy, cppcheck, clang-format)
- Dart/Flutter (dart analyze, dart format, very_good_analysis)

All operations use the existing terminal tool infrastructure.
"""

import json
import logging
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from tools.registry import registry
from tools.file_tools import _resolve_path_for_task, _get_file_ops
from tools.terminal_tool import terminal_tool

logger = logging.getLogger(__name__)


def _run_command(command: str, task_id: str = "default", timeout: int = 300) -> Dict[str, Any]:
    """Run a command via terminal tool."""
    try:
        result = terminal_tool(command=command, task_id=task_id, timeout=timeout)
        return json.loads(result)
    except Exception as e:
        logger.exception("Command failed: %s", e)
        return {"error": f"Command failed: {e}", "success": False}


def _resolve_path(path: str, task_id: str = "default") -> Path:
    """Resolve a path."""
    return _resolve_path_for_task(path, task_id)


def _get_file_ops(task_id: str = "default"):
    """Get file operations."""
    from tools.file_tools import _get_file_ops as get_file_ops
    return get_file_ops(task_id)


def _detect_language_project(repo_path: Path) -> Dict[str, bool]:
    """Detect which language projects exist in the repository."""
    file_ops = _get_file_ops()
    
    languages = {
        "rust": file_ops.exists(repo_path / "Cargo.toml"),
        "python": file_ops.exists(repo_path / "pyproject.toml") or file_ops.exists(repo_path / "setup.py") or file_ops.exists(repo_path / "requirements.txt"),
        "typescript": file_ops.exists(repo_path / "tsconfig.json") or file_ops.exists(repo_path / "package.json"),
        "javascript": file_ops.exists(repo_path / "package.json"),
        "go": file_ops.exists(repo_path / "go.mod"),
        "java": file_ops.exists(repo_path / "pom.xml") or file_ops.exists(repo_path / "build.gradle") or file_ops.exists(repo_path / "build.gradle.kts"),
        "kotlin": file_ops.exists(repo_path / "build.gradle.kts") or any(f.suffix == ".kt" for f in repo_path.rglob("*") if f.is_file()),
        "swift": file_ops.exists(repo_path / "Package.swift") or any(f.suffix == ".swift" for f in repo_path.rglob("*") if f.is_file()),
        "csharp": file_ops.exists(repo_path / "*.csproj") or file_ops.exists(repo_path / "*.sln"),
        "cpp": any(f.suffix in [".cpp", ".cc", ".cxx", ".hpp", ".h"] for f in repo_path.rglob("*") if f.is_file()),
        "dart": file_ops.exists(repo_path / "pubspec.yaml"),
    }
    
    return languages


# =============================================================================
# RUST
# =============================================================================

def rust_analyze(
    repo_path: str = ".",
    check: bool = True,
    clippy: bool = True,
    fmt_check: bool = True,
    tests: bool = False,
    doc: bool = False,
    deny_warnings: bool = False,
    extra_args: Optional[List[str]] = None,
    task_id: str = "default",
) -> str:
    """Run Rust analysis tools."""
    try:
        resolved = _resolve_path(repo_path, task_id)
        file_ops = _get_file_ops(task_id)
        
        if not file_ops.exists(resolved / "Cargo.toml"):
            return json.dumps({"error": f"Not a Rust project: {repo_path}"})
        
        results = {}
        
        if check:
            cmd = f"cd {resolved} && cargo check"
            if deny_warnings:
                cmd += " --deny warnings"
            if extra_args:
                cmd += " " + " ".join(extra_args)
            result = _run_command(cmd, task_id)
            results["check"] = {
                "success": result.get("success", False),
                "output": result.get("stdout", "") + result.get("stderr", ""),
            }
        
        if clippy:
            cmd = f"cd {resolved} && cargo clippy"
            if deny_warnings:
                cmd += " -- -D warnings"
            if extra_args:
                cmd += " " + " ".join(extra_args)
            result = _run_command(cmd, task_id)
            results["clippy"] = {
                "success": result.get("success", False),
                "output": result.get("stdout", "") + result.get("stderr", ""),
            }
        
        if fmt_check:
            cmd = f"cd {resolved} && cargo fmt --check"
            result = _run_command(cmd, task_id)
            results["fmt"] = {
                "success": result.get("success", False),
                "output": result.get("stdout", "") + result.get("stderr", ""),
            }
        
        if tests:
            cmd = f"cd {resolved} && cargo test"
            if extra_args:
                cmd += " " + " ".join(extra_args)
            result = _run_command(cmd, task_id, timeout=600)
            results["tests"] = {
                "success": result.get("success", False),
                "output": result.get("stdout", "") + result.get("stderr", ""),
            }
        
        if doc:
            cmd = f"cd {resolved} && cargo doc --no-deps"
            result = _run_command(cmd, task_id)
            results["doc"] = {
                "success": result.get("success", False),
                "output": result.get("stdout", "") + result.get("stderr", ""),
            }
        
        return json.dumps({
            "success": all(r.get("success", False) for r in results.values()),
            "results": results,
        })
    
    except Exception as e:
        logger.exception("rust_analyze error: %s", e)
        return json.dumps({"error": f"Rust analysis failed: {e}"})


def rust_fmt(
    repo_path: str = ".",
    check: bool = False,
    task_id: str = "default",
) -> str:
    """Format Rust code with rustfmt."""
    try:
        resolved = _resolve_path(repo_path, task_id)
        file_ops = _get_file_ops(task_id)
        
        if not file_ops.exists(resolved / "Cargo.toml"):
            return json.dumps({"error": f"Not a Rust project: {repo_path}"})
        
        cmd = f"cd {resolved} && cargo fmt"
        if check:
            cmd += " --check"
        
        result = _run_command(cmd, task_id)
        
        return json.dumps({
            "success": result.get("success", False),
            "output": result.get("stdout", "") + result.get("stderr", ""),
        })
    
    except Exception as e:
        logger.exception("rust_fmt error: %s", e)
        return json.dumps({"error": f"Rust fmt failed: {e}"})


# =============================================================================
# PYTHON
# =============================================================================

def python_analyze(
    repo_path: str = ".",
    mypy: bool = True,
    pyright: bool = False,
    ruff: bool = True,
    black_check: bool = True,
    pylint: bool = False,
    bandit: bool = False,
    extra_args: Optional[List[str]] = None,
    task_id: str = "default",
) -> str:
    """Run Python analysis tools."""
    try:
        resolved = _resolve_path(repo_path, task_id)
        file_ops = _get_file_ops(task_id)
        
        if not (file_ops.exists(resolved / "pyproject.toml") or file_ops.exists(resolved / "setup.py") or file_ops.exists(repo_path / "requirements.txt")):
            return json.dumps({"error": f"Not a Python project: {repo_path}"})
        
        results = {}
        
        # Find Python files
        python_files = [str(f.relative_to(resolved)) for f in resolved.rglob("*.py") if f.is_file()]
        if not python_files:
            return json.dumps({"error": "No Python files found"})
        
        files_arg = " ".join(python_files[:50])  # Limit
        
        if mypy:
            cmd = f"cd {resolved} && python -m mypy {files_arg}"
            if extra_args:
                cmd += " " + " ".join(extra_args)
            result = _run_command(cmd, task_id)
            results["mypy"] = {
                "success": result.get("success", False),
                "output": result.get("stdout", "") + result.get("stderr", ""),
            }
        
        if pyright:
            cmd = f"cd {resolved} && python -m pyright {files_arg}"
            result = _run_command(cmd, task_id)
            results["pyright"] = {
                "success": result.get("success", False),
                "output": result.get("stdout", "") + result.get("stderr", ""),
            }
        
        if ruff:
            cmd = f"cd {resolved} && python -m ruff check {files_arg}"
            if extra_args:
                cmd += " " + " ".join(extra_args)
            result = _run_command(cmd, task_id)
            results["ruff"] = {
                "success": result.get("success", False),
                "output": result.get("stdout", "") + result.get("stderr", ""),
            }
        
        if black_check:
            cmd = f"cd {resolved} && python -m black --check {files_arg}"
            result = _run_command(cmd, task_id)
            results["black"] = {
                "success": result.get("success", False),
                "output": result.get("stdout", "") + result.get("stderr", ""),
            }
        
        if pylint:
            cmd = f"cd {resolved} && python -m pylint {files_arg}"
            if extra_args:
                cmd += " " + " ".join(extra_args)
            result = _run_command(cmd, task_id)
            results["pylint"] = {
                "success": result.get("success", False),
                "output": result.get("stdout", "") + result.get("stderr", ""),
            }
        
        if bandit:
            cmd = f"cd {resolved} && python -m bandit -r {repo_path}"
            result = _run_command(cmd, task_id)
            results["bandit"] = {
                "success": result.get("success", False),
                "output": result.get("stdout", "") + result.get("stderr", ""),
            }
        
        return json.dumps({
            "success": all(r.get("success", False) for r in results.values()),
            "results": results,
        })
    
    except Exception as e:
        logger.exception("python_analyze error: %s", e)
        return json.dumps({"error": f"Python analysis failed: {e}"})


def python_format(
    repo_path: str = ".",
    black: bool = True,
    ruff_format: bool = True,
    isort: bool = True,
    task_id: str = "default",
) -> str:
    """Format Python code."""
    try:
        resolved = _resolve_path(repo_path, task_id)
        file_ops = _get_file_ops(task_id)
        
        results = {}
        python_files = [str(f.relative_to(resolved)) for f in resolved.rglob("*.py") if f.is_file()]
        if not python_files:
            return json.dumps({"error": "No Python files found"})
        
        files_arg = " ".join(python_files[:50])
        
        if isort:
            cmd = f"cd {resolved} && python -m isort {files_arg}"
            result = _run_command(cmd, task_id)
            results["isort"] = {
                "success": result.get("success", False),
                "output": result.get("stdout", "") + result.get("stderr", ""),
            }
        
        if black:
            cmd = f"cd {resolved} && python -m black {files_arg}"
            result = _run_command(cmd, task_id)
            results["black"] = {
                "success": result.get("success", False),
                "output": result.get("stdout", "") + result.get("stderr", ""),
            }
        
        if ruff_format:
            cmd = f"cd {resolved} && python -m ruff format {files_arg}"
            result = _run_command(cmd, task_id)
            results["ruff_format"] = {
                "success": result.get("success", False),
                "output": result.get("stdout", "") + result.get("stderr", ""),
            }
        
        return json.dumps({
            "success": all(r.get("success", False) for r in results.values()),
            "results": results,
        })
    
    except Exception as e:
        logger.exception("python_format error: %s", e)
        return json.dumps({"error": f"Python format failed: {e}"})


# =============================================================================
# TYPESCRIPT/JAVASCRIPT
# =============================================================================

def typescript_analyze(
    repo_path: str = ".",
    tsc: bool = True,
    eslint: bool = True,
    prettier_check: bool = True,
    biome: bool = False,
    extra_args: Optional[List[str]] = None,
    task_id: str = "default",
) -> str:
    """Run TypeScript/JavaScript analysis tools."""
    try:
        resolved = _resolve_path(repo_path, task_id)
        file_ops = _get_file_ops(task_id)
        
        if not file_ops.exists(resolved / "package.json"):
            return json.dumps({"error": f"No package.json found: {repo_path}"})
        
        pkg = json.loads(file_ops.read(resolved / "package.json"))
        dev_deps = pkg.get("devDependencies", {})
        deps = pkg.get("dependencies", {})
        all_deps = {**dev_deps, **deps}
        
        results = {}
        
        if tsc and "typescript" in all_deps:
            cmd = f"cd {resolved} && npx tsc --noEmit"
            if extra_args:
                cmd += " " + " ".join(extra_args)
            result = _run_command(cmd, task_id)
            results["tsc"] = {
                "success": result.get("success", False),
                "output": result.get("stdout", "") + result.get("stderr", ""),
            }
        
        if eslint and "eslint" in all_deps:
            cmd = f"cd {resolved} && npx eslint . --ext .ts,.tsx,.js,.jsx"
            if extra_args:
                cmd += " " + " ".join(extra_args)
            result = _run_command(cmd, task_id)
            results["eslint"] = {
                "success": result.get("success", False),
                "output": result.get("stdout", "") + result.get("stderr", ""),
            }
        
        if prettier_check and "prettier" in all_deps:
            cmd = f"cd {resolved} && npx prettier --check ."
            result = _run_command(cmd, task_id)
            results["prettier"] = {
                "success": result.get("success", False),
                "output": result.get("stdout", "") + result.get("stderr", ""),
            }
        
        if biome and "@biomejs/biome" in all_deps:
            cmd = f"cd {resolved} && npx biome check ."
            result = _run_command(cmd, task_id)
            results["biome"] = {
                "success": result.get("success", False),
                "output": result.get("stdout", "") + result.get("stderr", ""),
            }
        
        return json.dumps({
            "success": all(r.get("success", False) for r in results.values()),
            "results": results,
        })
    
    except Exception as e:
        logger.exception("typescript_analyze error: %s", e)
        return json.dumps({"error": f"TypeScript analysis failed: {e}"})


def typescript_format(
    repo_path: str = ".",
    prettier: bool = True,
    eslint_fix: bool = True,
    biome_format: bool = False,
    task_id: str = "default",
) -> str:
    """Format TypeScript/JavaScript code."""
    try:
        resolved = _resolve_path(repo_path, task_id)
        file_ops = _get_file_ops(task_id)
        
        if not file_ops.exists(resolved / "package.json"):
            return json.dumps({"error": f"No package.json found: {repo_path}"})
        
        pkg = json.loads(file_ops.read(resolved / "package.json"))
        dev_deps = pkg.get("devDependencies", {})
        deps = pkg.get("dependencies", {})
        all_deps = {**dev_deps, **deps}
        
        results = {}
        
        if prettier and "prettier" in all_deps:
            cmd = f"cd {resolved} && npx prettier --write ."
            result = _run_command(cmd, task_id)
            results["prettier"] = {
                "success": result.get("success", False),
                "output": result.get("stdout", "") + result.get("stderr", ""),
            }
        
        if eslint_fix and "eslint" in all_deps:
            cmd = f"cd {resolved} && npx eslint . --ext .ts,.tsx,.js,.jsx --fix"
            result = _run_command(cmd, task_id)
            results["eslint_fix"] = {
                "success": result.get("success", False),
                "output": result.get("stdout", "") + result.get("stderr", ""),
            }
        
        if biome_format and "@biomejs/biome" in all_deps:
            cmd = f"cd {resolved} && npx biome format --write ."
            result = _run_command(cmd, task_id)
            results["biome_format"] = {
                "success": result.get("success", False),
                "output": result.get("stdout", "") + result.get("stderr", ""),
            }
        
        return json.dumps({
            "success": all(r.get("success", False) for r in results.values()),
            "results": results,
        })
    
    except Exception as e:
        logger.exception("typescript_format error: %s", e)
        return json.dumps({"error": f"TypeScript format failed: {e}"})


# =============================================================================
# GO
# =============================================================================

def go_analyze(
    repo_path: str = ".",
    vet: bool = True,
    staticcheck: bool = True,
    golangci_lint: bool = True,
    gofmt_check: bool = True,
    extra_args: Optional[List[str]] = None,
    task_id: str = "default",
) -> str:
    """Run Go analysis tools."""
    try:
        resolved = _resolve_path(repo_path, task_id)
        file_ops = _get_file_ops(task_id)
        
        if not file_ops.exists(resolved / "go.mod"):
            return json.dumps({"error": f"Not a Go module: {repo_path}"})
        
        results = {}
        
        if vet:
            cmd = f"cd {resolved} && go vet ./..."
            if extra_args:
                cmd += " " + " ".join(extra_args)
            result = _run_command(cmd, task_id)
            results["vet"] = {
                "success": result.get("success", False),
                "output": result.get("stdout", "") + result.get("stderr", ""),
            }
        
        if staticcheck:
            cmd = f"cd {resolved} && staticcheck ./..."
            result = _run_command(cmd, task_id)
            results["staticcheck"] = {
                "success": result.get("success", False),
                "output": result.get("stdout", "") + result.get("stderr", ""),
            }
        
        if golangci_lint:
            cmd = f"cd {resolved} && golangci-lint run ./..."
            if extra_args:
                cmd += " " + " ".join(extra_args)
            result = _run_command(cmd, task_id)
            results["golangci_lint"] = {
                "success": result.get("success", False),
                "output": result.get("stdout", "") + result.get("stderr", ""),
            }
        
        if gofmt_check:
            cmd = f"cd {resolved} && gofmt -l ."
            result = _run_command(cmd, task_id)
            results["gofmt"] = {
                "success": result.get("success", False),
                "output": result.get("stdout", "") + result.get("stderr", ""),
            }
        
        return json.dumps({
            "success": all(r.get("success", False) for r in results.values()),
            "results": results,
        })
    
    except Exception as e:
        logger.exception("go_analyze error: %s", e)
        return json.dumps({"error": f"Go analysis failed: {e}"})


def go_format(
    repo_path: str = ".",
    gofmt: bool = True,
    goimports: bool = True,
    task_id: str = "default",
) -> str:
    """Format Go code."""
    try:
        resolved = _resolve_path(repo_path, task_id)
        file_ops = _get_file_ops(task_id)
        
        if not file_ops.exists(resolved / "go.mod"):
            return json.dumps({"error": f"Not a Go module: {repo_path}"})
        
        results = {}
        
        if gofmt:
            cmd = f"cd {resolved} && gofmt -w ."
            result = _run_command(cmd, task_id)
            results["gofmt"] = {
                "success": result.get("success", False),
                "output": result.get("stdout", "") + result.get("stderr", ""),
            }
        
        if goimports:
            cmd = f"cd {resolved} && goimports -w ."
            result = _run_command(cmd, task_id)
            results["goimports"] = {
                "success": result.get("success", False),
                "output": result.get("stdout", "") + result.get("stderr", ""),
            }
        
        return json.dumps({
            "success": all(r.get("success", False) for r in results.values()),
            "results": results,
        })
    
    except Exception as e:
        logger.exception("go_format error: %s", e)
        return json.dumps({"error": f"Go format failed: {e}"})


# =============================================================================
# JAVA
# =============================================================================

def java_analyze(
    repo_path: str = ".",
    checkstyle: bool = True,
    spotbugs: bool = True,
    pmd: bool = True,
    google_java_format_check: bool = True,
    build_tool: str = "auto",  # auto, maven, gradle
    extra_args: Optional[List[str]] = None,
    task_id: str = "default",
) -> str:
    """Run Java analysis tools."""
    try:
        resolved = _resolve_path(repo_path, task_id)
        file_ops = _get_file_ops(task_id)
        
        has_maven = file_ops.exists(resolved / "pom.xml")
        has_gradle = file_ops.exists(resolved / "build.gradle") or file_ops.exists(resolved / "build.gradle.kts")
        
        if build_tool == "auto":
            if has_gradle:
                build_tool = "gradle"
            elif has_maven:
                build_tool = "maven"
            else:
                return json.dumps({"error": "No Maven or Gradle build file found"})
        
        results = {}
        
        if build_tool == "maven":
            if checkstyle:
                cmd = f"cd {resolved} && mvn checkstyle:check"
                if extra_args:
                    cmd += " " + " ".join(extra_args)
                result = _run_command(cmd, task_id)
                results["checkstyle"] = {
                    "success": result.get("success", False),
                    "output": result.get("stdout", "") + result.get("stderr", ""),
                }
            
            if spotbugs:
                cmd = f"cd {resolved} && mvn spotbugs:check"
                result = _run_command(cmd, task_id)
                results["spotbugs"] = {
                    "success": result.get("success", False),
                    "output": result.get("stdout", "") + result.get("stderr", ""),
                }
            
            if pmd:
                cmd = f"cd {resolved} && mvn pmd:check"
                result = _run_command(cmd, task_id)
                results["pmd"] = {
                    "success": result.get("success", False),
                    "output": result.get("stdout", "") + result.get("stderr", ""),
                }
            
            if google_java_format_check:
                cmd = f"cd {resolved} && mvn com.google.code.maven-replacer-plugin:replacer:1.5.3:replace -Dgoogle.java.format=true"
                result = _run_command(cmd, task_id)
                results["google_java_format"] = {
                    "success": result.get("success", False),
                    "output": result.get("stdout", "") + result.get("stderr", ""),
                }
        else:
            # Gradle
            if checkstyle:
                cmd = f"cd {resolved} && ./gradlew checkstyleMain"
                result = _run_command(cmd, task_id)
                results["checkstyle"] = {
                    "success": result.get("success", False),
                    "output": result.get("stdout", "") + result.get("stderr", ""),
                }
            
            if spotbugs:
                cmd = f"cd {resolved} && ./gradlew spotbugsMain"
                result = _run_command(cmd, task_id)
                results["spotbugs"] = {
                    "success": result.get("success", False),
                    "output": result.get("stdout", "") + result.get("stderr", ""),
                }
            
            if pmd:
                cmd = f"cd {resolved} && ./gradlew pmdMain"
                result = _run_command(cmd, task_id)
                results["pmd"] = {
                    "success": result.get("success", False),
                    "output": result.get("stdout", "") + result.get("stderr", ""),
                }
        
        return json.dumps({
            "success": all(r.get("success", False) for r in results.values()),
            "results": results,
        })
    
    except Exception as e:
        logger.exception("java_analyze error: %s", e)
        return json.dumps({"error": f"Java analysis failed: {e}"})


# =============================================================================
# KOTLIN
# =============================================================================

def kotlin_analyze(
    repo_path: str = ".",
    detekt: bool = True,
    ktlint: bool = True,
    extra_args: Optional[List[str]] = None,
    task_id: str = "default",
) -> str:
    """Run Kotlin analysis tools."""
    try:
        resolved = _resolve_path(repo_path, task_id)
        file_ops = _get_file_ops(task_id)
        
        if not (file_ops.exists(resolved / "build.gradle.kts") or any(f.suffix == ".kt" for f in resolved.rglob("*") if f.is_file())):
            return json.dumps({"error": f"Not a Kotlin project: {repo_path}"})
        
        results = {}
        
        if detekt:
            cmd = f"cd {resolved} && ./gradlew detekt"
            if extra_args:
                cmd += " " + " ".join(extra_args)
            result = _run_command(cmd, task_id)
            results["detekt"] = {
                "success": result.get("success", False),
                "output": result.get("stdout", "") + result.get("stderr", ""),
            }
        
        if ktlint:
            cmd = f"cd {resolved} && ./gradlew ktlintCheck"
            result = _run_command(cmd, task_id)
            results["ktlint"] = {
                "success": result.get("success", False),
                "output": result.get("stdout", "") + result.get("stderr", ""),
            }
        
        return json.dumps({
            "success": all(r.get("success", False) for r in results.values()),
            "results": results,
        })
    
    except Exception as e:
        logger.exception("kotlin_analyze error: %s", e)
        return json.dumps({"error": f"Kotlin analysis failed: {e}"})


def kotlin_format(
    repo_path: str = ".",
    ktlint_format: bool = True,
    task_id: str = "default",
) -> str:
    """Format Kotlin code."""
    try:
        resolved = _resolve_path(repo_path, task_id)
        file_ops = _get_file_ops(task_id)
        
        results = {}
        
        if ktlint_format:
            cmd = f"cd {resolved} && ./gradlew ktlintFormat"
            result = _run_command(cmd, task_id)
            results["ktlint_format"] = {
                "success": result.get("success", False),
                "output": result.get("stdout", "") + result.get("stderr", ""),
            }
        
        return json.dumps({
            "success": all(r.get("success", False) for r in results.values()),
            "results": results,
        })
    
    except Exception as e:
        logger.exception("kotlin_format error: %s", e)
        return json.dumps({"error": f"Kotlin format failed: {e}"})


# =============================================================================
# SWIFT
# =============================================================================

def swift_analyze(
    repo_path: str = ".",
    swiftlint: bool = True,
    swiftformat_check: bool = True,
    xcodebuild: bool = False,
    extra_args: Optional[List[str]] = None,
    task_id: str = "default",
) -> str:
    """Run Swift analysis tools."""
    try:
        resolved = _resolve_path(repo_path, task_id)
        file_ops = _get_file_ops(task_id)
        
        if not (file_ops.exists(resolved / "Package.swift") or any(f.suffix == ".swift" for f in resolved.rglob("*") if f.is_file())):
            return json.dumps({"error": f"Not a Swift project: {repo_path}"})
        
        results = {}
        
        if swiftlint:
            cmd = f"cd {resolved} && swiftlint lint"
            if extra_args:
                cmd += " " + " ".join(extra_args)
            result = _run_command(cmd, task_id)
            results["swiftlint"] = {
                "success": result.get("success", False),
                "output": result.get("stdout", "") + result.get("stderr", ""),
            }
        
        if swiftformat_check:
            cmd = f"cd {resolved} && swiftformat --lint ."
            result = _run_command(cmd, task_id)
            results["swiftformat"] = {
                "success": result.get("success", False),
                "output": result.get("stdout", "") + result.get("stderr", ""),
            }
        
        if xcodebuild:
            cmd = f"cd {resolved} && xcodebuild analyze"
            result = _run_command(cmd, task_id, timeout=600)
            results["xcodebuild"] = {
                "success": result.get("success", False),
                "output": result.get("stdout", "") + result.get("stderr", ""),
            }
        
        return json.dumps({
            "success": all(r.get("success", False) for r in results.values()),
            "results": results,
        })
    
    except Exception as e:
        logger.exception("swift_analyze error: %s", e)
        return json.dumps({"error": f"Swift analysis failed: {e}"})


def swift_format(
    repo_path: str = ".",
    swiftformat: bool = True,
    swiftlint_autocorrect: bool = True,
    task_id: str = "default",
) -> str:
    """Format Swift code."""
    try:
        resolved = _resolve_path(repo_path, task_id)
        file_ops = _get_file_ops(task_id)
        
        results = {}
        
        if swiftformat:
            cmd = f"cd {resolved} && swiftformat ."
            result = _run_command(cmd, task_id)
            results["swiftformat"] = {
                "success": result.get("success", False),
                "output": result.get("stdout", "") + result.get("stderr", ""),
            }
        
        if swiftlint_autocorrect:
            cmd = f"cd {resolved} && swiftlint autocorrect"
            result = _run_command(cmd, task_id)
            results["swiftlint_autocorrect"] = {
                "success": result.get("success", False),
                "output": result.get("stdout", "") + result.get("stderr", ""),
            }
        
        return json.dumps({
            "success": all(r.get("success", False) for r in results.values()),
            "results": results,
        })
    
    except Exception as e:
        logger.exception("swift_format error: %s", e)
        return json.dumps({"error": f"Swift format failed: {e}"})


# =============================================================================
# C#
# =============================================================================

def csharp_analyze(
    repo_path: str = ".",
    dotnet_format_check: bool = True,
    roslynator: bool = True,
    sonaranalyzer: bool = False,
    build: bool = True,
    extra_args: Optional[List[str]] = None,
    task_id: str = "default",
) -> str:
    """Run C# analysis tools."""
    try:
        resolved = _resolve_path(repo_path, task_id)
        file_ops = _get_file_ops(task_id)
        
        # Check for C# project
        csproj_files = list(resolved.rglob("*.csproj"))
        sln_files = list(resolved.rglob("*.sln"))
        
        if not csproj_files and not sln_files:
            return json.dumps({"error": f"No C# project found: {repo_path}"})
        
        results = {}
        project = sln_files[0] if sln_files else csproj_files[0]
        
        if build:
            cmd = f"cd {resolved} && dotnet build {project}"
            result = _run_command(cmd, task_id)
            results["build"] = {
                "success": result.get("success", False),
                "output": result.get("stdout", "") + result.get("stderr", ""),
            }
        
        if dotnet_format_check:
            cmd = f"cd {resolved} && dotnet format {project} --verify-no-changes"
            result = _run_command(cmd, task_id)
            results["dotnet_format"] = {
                "success": result.get("success", False),
                "output": result.get("stdout", "") + result.get("stderr", ""),
            }
        
        if roslynator:
            cmd = f"cd {resolved} && dotnet roslynator analyze {project}"
            if extra_args:
                cmd += " " + " ".join(extra_args)
            result = _run_command(cmd, task_id)
            results["roslynator"] = {
                "success": result.get("success", False),
                "output": result.get("stdout", "") + result.get("stderr", ""),
            }
        
        if sonaranalyzer:
            cmd = f"cd {resolved} && dotnet sonarscanner begin /k:project && dotnet build {project} && dotnet sonarscanner end"
            result = _run_command(cmd, task_id, timeout=600)
            results["sonaranalyzer"] = {
                "success": result.get("success", False),
                "output": result.get("stdout", "") + result.get("stderr", ""),
            }
        
        return json.dumps({
            "success": all(r.get("success", False) for r in results.values()),
            "results": results,
        })
    
    except Exception as e:
        logger.exception("csharp_analyze error: %s", e)
        return json.dumps({"error": f"C# analysis failed: {e}"})


def csharp_format(
    repo_path: str = ".",
    dotnet_format: bool = True,
    task_id: str = "default",
) -> str:
    """Format C# code."""
    try:
        resolved = _resolve_path(repo_path, task_id)
        file_ops = _get_file_ops(task_id)
        
        csproj_files = list(resolved.rglob("*.csproj"))
        sln_files = list(resolved.rglob("*.sln"))
        
        if not csproj_files and not sln_files:
            return json.dumps({"error": f"No C# project found: {repo_path}"})
        
        project = sln_files[0] if sln_files else csproj_files[0]
        results = {}
        
        if dotnet_format:
            cmd = f"cd {resolved} && dotnet format {project}"
            result = _run_command(cmd, task_id)
            results["dotnet_format"] = {
                "success": result.get("success", False),
                "output": result.get("stdout", "") + result.get("stderr", ""),
            }
        
        return json.dumps({
            "success": all(r.get("success", False) for r in results.values()),
            "results": results,
        })
    
    except Exception as e:
        logger.exception("csharp_format error: %s", e)
        return json.dumps({"error": f"C# format failed: {e}"})


# =============================================================================
# C++
# =============================================================================

def cpp_analyze(
    repo_path: str = ".",
    clang_tidy: bool = True,
    cppcheck: bool = True,
    clang_format_check: bool = True,
    cmake: bool = False,
    extra_args: Optional[List[str]] = None,
    task_id: str = "default",
) -> str:
    """Run C++ analysis tools."""
    try:
        resolved = _resolve_path(repo_path, task_id)
        file_ops = _get_file_ops(task_id)
        
        # Check for C++ files
        cpp_files = list(resolved.rglob("*.cpp")) + list(resolved.rglob("*.cc")) + list(resolved.rglob("*.cxx")) + list(resolved.rglob("*.hpp")) + list(resolved.rglob("*.h"))
        
        if not cpp_files:
            return json.dumps({"error": f"No C++ files found: {repo_path}"})
        
        results = {}
        
        if clang_tidy:
            cmd = f"cd {resolved} && clang-tidy " + " ".join(str(f.relative_to(resolved)) for f in cpp_files[:20])
            if extra_args:
                cmd += " " + " ".join(extra_args)
            result = _run_command(cmd, task_id)
            results["clang_tidy"] = {
                "success": result.get("success", False),
                "output": result.get("stdout", "") + result.get("stderr", ""),
            }
        
        if cppcheck:
            cmd = f"cd {resolved} && cppcheck --enable=all --inline-suppr ."
            result = _run_command(cmd, task_id)
            results["cppcheck"] = {
                "success": result.get("success", False),
                "output": result.get("stdout", "") + result.get("stderr", ""),
            }
        
        if clang_format_check:
            cmd = f"cd {resolved} && clang-format --dry-run --Werror " + " ".join(str(f.relative_to(resolved)) for f in cpp_files[:20])
            result = _run_command(cmd, task_id)
            results["clang_format"] = {
                "success": result.get("success", False),
                "output": result.get("stdout", "") + result.get("stderr", ""),
            }
        
        if cmake and file_ops.exists(resolved / "CMakeLists.txt"):
            build_dir = resolved / "build"
            build_dir.mkdir(exist_ok=True)
            cmd = f"cd {build_dir} && cmake .. && make"
            result = _run_command(cmd, task_id, timeout=600)
            results["cmake"] = {
                "success": result.get("success", False),
                "output": result.get("stdout", "") + result.get("stderr", ""),
            }
        
        return json.dumps({
            "success": all(r.get("success", False) for r in results.values()),
            "results": results,
        })
    
    except Exception as e:
        logger.exception("cpp_analyze error: %s", e)
        return json.dumps({"error": f"C++ analysis failed: {e}"})


def cpp_format(
    repo_path: str = ".",
    clang_format: bool = True,
    task_id: str = "default",
) -> str:
    """Format C++ code."""
    try:
        resolved = _resolve_path(repo_path, task_id)
        file_ops = _get_file_ops(task_id)
        
        cpp_files = list(resolved.rglob("*.cpp")) + list(resolved.rglob("*.cc")) + list(resolved.rglob("*.cxx")) + list(resolved.rglob("*.hpp")) + list(resolved.rglob("*.h"))
        
        if not cpp_files:
            return json.dumps({"error": f"No C++ files found: {repo_path}"})
        
        results = {}
        
        if clang_format:
            cmd = f"cd {resolved} && clang-format -i " + " ".join(str(f.relative_to(resolved)) for f in cpp_files[:50])
            result = _run_command(cmd, task_id)
            results["clang_format"] = {
                "success": result.get("success", False),
                "output": result.get("stdout", "") + result.get("stderr", ""),
            }
        
        return json.dumps({
            "success": all(r.get("success", False) for r in results.values()),
            "results": results,
        })
    
    except Exception as e:
        logger.exception("cpp_format error: %s", e)
        return json.dumps({"error": f"C++ format failed: {e}"})


# =============================================================================
# DART/FLUTTER
# =============================================================================

def dart_analyze(
    repo_path: str = ".",
    dart_analyze_cmd: bool = True,
    dart_format_check: bool = True,
    very_good_analysis: bool = False,
    extra_args: Optional[List[str]] = None,
    task_id: str = "default",
) -> str:
    """Run Dart/Flutter analysis tools."""
    try:
        resolved = _resolve_path(repo_path, task_id)
        file_ops = _get_file_ops(task_id)
        
        if not file_ops.exists(resolved / "pubspec.yaml"):
            return json.dumps({"error": f"Not a Dart/Flutter project: {repo_path}"})
        
        results = {}
        
        if dart_analyze_cmd:
            cmd = f"cd {resolved} && dart analyze"
            if extra_args:
                cmd += " " + " ".join(extra_args)
            result = _run_command(cmd, task_id)
            results["dart_analyze"] = {
                "success": result.get("success", False),
                "output": result.get("stdout", "") + result.get("stderr", ""),
            }
        
        if dart_format_check:
            cmd = f"cd {resolved} && dart format --set-exit-if-changed ."
            result = _run_command(cmd, task_id)
            results["dart_format"] = {
                "success": result.get("success", False),
                "output": result.get("stdout", "") + result.get("stderr", ""),
            }
        
        if very_good_analysis:
            cmd = f"cd {resolved} && dart run very_good_analysis"
            result = _run_command(cmd, task_id)
            results["very_good_analysis"] = {
                "success": result.get("success", False),
                "output": result.get("stdout", "") + result.get("stderr", ""),
            }
        
        return json.dumps({
            "success": all(r.get("success", False) for r in results.values()),
            "results": results,
        })
    
    except Exception as e:
        logger.exception("dart_analyze error: %s", e)
        return json.dumps({"error": f"Dart analysis failed: {e}"})


def dart_format(
    repo_path: str = ".",
    dart_format_cmd: bool = True,
    task_id: str = "default",
) -> str:
    """Format Dart code."""
    try:
        resolved = _resolve_path(repo_path, task_id)
        file_ops = _get_file_ops(task_id)
        
        if not file_ops.exists(resolved / "pubspec.yaml"):
            return json.dumps({"error": f"Not a Dart/Flutter project: {repo_path}"})
        
        results = {}
        
        if dart_format_cmd:
            cmd = f"cd {resolved} && dart format ."
            result = _run_command(cmd, task_id)
            results["dart_format"] = {
                "success": result.get("success", False),
                "output": result.get("stdout", "") + result.get("stderr", ""),
            }
        
        return json.dumps({
            "success": all(r.get("success", False) for r in results.values()),
            "results": results,
        })
    
    except Exception as e:
        logger.exception("dart_format error: %s", e)
        return json.dumps({"error": f"Dart format failed: {e}"})


# =============================================================================
# UNIVERSAL
# =============================================================================

def detect_languages(
    repo_path: str = ".",
    task_id: str = "default",
) -> str:
    """Detect languages in a project."""
    try:
        resolved = _resolve_path(repo_path, task_id)
        file_ops = _get_file_ops(task_id)
        
        if not file_ops.exists(resolved):
            return json.dumps({"error": f"Path not found: {repo_path}"})
        
        languages = _detect_language_project(resolved)
        
        # Count files per language
        extensions = {}
        for f in resolved.rglob("*"):
            if f.is_file():
                ext = f.suffix.lower()
                if ext:
                    extensions[ext] = extensions.get(ext, 0) + 1
        
        return json.dumps({
            "languages": {k: v for k, v in languages.items() if v},
            "extensions": dict(sorted(extensions.items(), key=lambda x: -x[1])[:20]),
        })
    
    except Exception as e:
        logger.exception("detect_languages error: %s", e)
        return json.dumps({"error": f"Language detection failed: {e}"})


def analyze_all(
    repo_path: str = ".",
    task_id: str = "default",
) -> str:
    """Run analysis for all detected languages."""
    try:
        resolved = _resolve_path(repo_path, task_id)
        file_ops = _get_file_ops(task_id)
        
        if not file_ops.exists(resolved):
            return json.dumps({"error": f"Path not found: {repo_path}"})
        
        languages = _detect_language_project(resolved)
        detected = [k for k, v in languages.items() if v]
        
        if not detected:
            return json.dumps({"error": "No supported languages detected"})
        
        results = {}
        
        # Run analysis for each detected language
        if languages.get("rust"):
            results["rust"] = json.loads(rust_analyze(repo_path, task_id=task_id))
        if languages.get("python"):
            results["python"] = json.loads(python_analyze(repo_path, task_id=task_id))
        if languages.get("typescript") or languages.get("javascript"):
            results["typescript"] = json.loads(typescript_analyze(repo_path, task_id=task_id))
        if languages.get("go"):
            results["go"] = json.loads(go_analyze(repo_path, task_id=task_id))
        if languages.get("java"):
            results["java"] = json.loads(java_analyze(repo_path, task_id=task_id))
        if languages.get("kotlin"):
            results["kotlin"] = json.loads(kotlin_analyze(repo_path, task_id=task_id))
        if languages.get("swift"):
            results["swift"] = json.loads(swift_analyze(repo_path, task_id=task_id))
        if languages.get("csharp"):
            results["csharp"] = json.loads(csharp_analyze(repo_path, task_id=task_id))
        if languages.get("cpp"):
            results["cpp"] = json.loads(cpp_analyze(repo_path, task_id=task_id))
        if languages.get("dart"):
            results["dart"] = json.loads(dart_analyze(repo_path, task_id=task_id))
        
        return json.dumps({
            "detected_languages": detected,
            "results": results,
        })
    
    except Exception as e:
        logger.exception("analyze_all error: %s", e)
        return json.dumps({"error": f"Full analysis failed: {e}"})


def detect_languages(
    repo_path: str = ".",
    task_id: str = "default",
) -> str:
    """Detect programming languages in a project."""
    try:
        resolved = _resolve_path(repo_path, task_id)
        file_ops = _get_file_ops(task_id)
        
        if not file_ops.exists(resolved):
            return json.dumps({"error": f"Path not found: {repo_path}"})
        
        languages = _detect_language_project(resolved)
        
        return json.dumps({
            "languages": {k: v for k, v in languages.items() if v},
        })
    
    except Exception as e:
        logger.exception("detect_languages error: %s", e)
        return json.dumps({"error": f"Language detection failed: {e}"})


def analyze_all(
    repo_path: str = ".",
    task_id: str = "default",
) -> str:
    """Run analysis for all detected languages in project."""
    try:
        resolved = _resolve_path(repo_path, task_id)
        file_ops = _get_file_ops(task_id)
        
        if not file_ops.exists(resolved):
            return json.dumps({"error": f"Path not found: {repo_path}"})
        
        languages = _detect_language_project(resolved)
        results = {}
        
        # This would call each language's analyze function
        # For now, just return detected languages
        return json.dumps({
            "detected_languages": {k: v for k, v in languages.items() if v},
            "message": "Use individual language analyze tools for detailed analysis",
        })
    
    except Exception as e:
        logger.exception("analyze_all error: %s", e)
        return json.dumps({"error": f"Analyze all failed: {e}"})


# Register all tools
def _register_language_tools():
    """Register all language support tools with the registry."""

    tools = [
        # Rust
        ("rust_analyze", "language_support", {
            "name": "rust_analyze",
            "description": "Run Rust analysis (cargo check, clippy, fmt, test, doc)",
            "parameters": {
                "type": "object",
                "properties": {
                    "repo_path": {"type": "string", "description": "Repository path", "default": "."},
                    "check": {"type": "boolean", "description": "Run cargo check", "default": True},
                    "clippy": {"type": "boolean", "description": "Run cargo clippy", "default": True},
                    "fmt_check": {"type": "boolean", "description": "Run cargo fmt --check", "default": True},
                    "tests": {"type": "boolean", "description": "Run cargo test", "default": False},
                    "doc": {"type": "boolean", "description": "Run cargo doc", "default": False},
                    "deny_warnings": {"type": "boolean", "description": "Deny warnings", "default": False},
                    "extra_args": {"type": "array", "items": {"type": "string"}, "description": "Extra cargo args", "default": None},
                },
                "required": [],
            },
        }, rust_analyze, None, [], False, "🦀", None),

        ("rust_fmt", "language_support", {
            "name": "rust_fmt",
            "description": "Format Rust code with rustfmt",
            "parameters": {
                "type": "object",
                "properties": {
                    "repo_path": {"type": "string", "description": "Repository path", "default": "."},
                    "check": {"type": "boolean", "description": "Check only, don't modify", "default": False},
                },
                "required": [],
            },
        }, rust_fmt, None, [], False, "🦀", None),

        # Python
        ("python_analyze", "language_support", {
            "name": "python_analyze",
            "description": "Run Python analysis (mypy, pyright, ruff, black, pylint, bandit)",
            "parameters": {
                "type": "object",
                "properties": {
                    "repo_path": {"type": "string", "description": "Repository path", "default": "."},
                    "mypy": {"type": "boolean", "description": "Run mypy", "default": True},
                    "pyright": {"type": "boolean", "description": "Run pyright", "default": False},
                    "ruff": {"type": "boolean", "description": "Run ruff", "default": True},
                    "black_check": {"type": "boolean", "description": "Run black --check", "default": True},
                    "pylint": {"type": "boolean", "description": "Run pylint", "default": False},
                    "bandit": {"type": "boolean", "description": "Run bandit security", "default": False},
                    "extra_args": {"type": "array", "items": {"type": "string"}, "description": "Extra args", "default": None},
                },
                "required": [],
            },
        }, python_analyze, None, [], False, "🐍", None),

        ("python_format", "language_support", {
            "name": "python_format",
            "description": "Format Python code (isort, black, ruff format)",
            "parameters": {
                "type": "object",
                "properties": {
                    "repo_path": {"type": "string", "description": "Repository path", "default": "."},
                    "black": {"type": "boolean", "description": "Run black", "default": True},
                    "ruff_format": {"type": "boolean", "description": "Run ruff format", "default": True},
                    "isort": {"type": "boolean", "description": "Run isort", "default": True},
                },
                "required": [],
            },
        }, python_format, None, [], False, "🐍", None),

        # TypeScript/JavaScript
        ("typescript_analyze", "language_support", {
            "name": "typescript_analyze",
            "description": "Run TypeScript/JS analysis (tsc, eslint, prettier, biome)",
            "parameters": {
                "type": "object",
                "properties": {
                    "repo_path": {"type": "string", "description": "Repository path", "default": "."},
                    "tsc": {"type": "boolean", "description": "Run tsc --noEmit", "default": True},
                    "eslint": {"type": "boolean", "description": "Run eslint", "default": True},
                    "prettier_check": {"type": "boolean", "description": "Run prettier --check", "default": True},
                    "biome": {"type": "boolean", "description": "Run biome check", "default": False},
                    "extra_args": {"type": "array", "items": {"type": "string"}, "description": "Extra args", "default": None},
                },
                "required": [],
            },
        }, typescript_analyze, None, [], False, "📘", None),

        ("typescript_format", "language_support", {
            "name": "typescript_format",
            "description": "Format TypeScript/JS code (prettier, eslint --fix, biome)",
            "parameters": {
                "type": "object",
                "properties": {
                    "repo_path": {"type": "string", "description": "Repository path", "default": "."},
                    "prettier": {"type": "boolean", "description": "Run prettier --write", "default": True},
                    "eslint_fix": {"type": "boolean", "description": "Run eslint --fix", "default": True},
                    "biome_format": {"type": "boolean", "description": "Run biome format --write", "default": False},
                },
                "required": [],
            },
        }, typescript_format, None, [], False, "📘", None),

        # Go
        ("go_analyze", "language_support", {
            "name": "go_analyze",
            "description": "Run Go analysis (go vet, staticcheck, golangci-lint, gofmt)",
            "parameters": {
                "type": "object",
                "properties": {
                    "repo_path": {"type": "string", "description": "Repository path", "default": "."},
                    "vet": {"type": "boolean", "description": "Run go vet", "default": True},
                    "staticcheck": {"type": "boolean", "description": "Run staticcheck", "default": True},
                    "golangci_lint": {"type": "boolean", "description": "Run golangci-lint", "default": True},
                    "gofmt_check": {"type": "boolean", "description": "Run gofmt -l", "default": True},
                    "extra_args": {"type": "array", "items": {"type": "string"}, "description": "Extra args", "default": None},
                },
                "required": [],
            },
        }, go_analyze, None, [], False, "🐹", None),

        ("go_format", "language_support", {
            "name": "go_format",
            "description": "Format Go code (gofmt, goimports)",
            "parameters": {
                "type": "object",
                "properties": {
                    "repo_path": {"type": "string", "description": "Repository path", "default": "."},
                    "gofmt": {"type": "boolean", "description": "Run gofmt -w", "default": True},
                    "goimports": {"type": "boolean", "description": "Run goimports -w", "default": True},
                },
                "required": [],
            },
        }, go_format, None, [], False, "🐹", None),

        # Java
        ("java_analyze", "language_support", {
            "name": "java_analyze",
            "description": "Run Java analysis (checkstyle, spotbugs, pmd, google-java-format)",
            "parameters": {
                "type": "object",
                "properties": {
                    "repo_path": {"type": "string", "description": "Repository path", "default": "."},
                    "checkstyle": {"type": "boolean", "description": "Run checkstyle", "default": True},
                    "spotbugs": {"type": "boolean", "description": "Run spotbugs", "default": True},
                    "pmd": {"type": "boolean", "description": "Run pmd", "default": True},
                    "google_java_format_check": {"type": "boolean", "description": "Check google-java-format", "default": True},
                    "build_tool": {"type": "string", "enum": ["auto", "maven", "gradle"], "default": "auto"},
                    "extra_args": {"type": "array", "items": {"type": "string"}, "description": "Extra args", "default": None},
                },
                "required": [],
            },
        }, java_analyze, None, [], False, "☕", None),

        # Kotlin
        ("kotlin_analyze", "language_support", {
            "name": "kotlin_analyze",
            "description": "Run Kotlin analysis (detekt, ktlint)",
            "parameters": {
                "type": "object",
                "properties": {
                    "repo_path": {"type": "string", "description": "Repository path", "default": "."},
                    "detekt": {"type": "boolean", "description": "Run detekt", "default": True},
                    "ktlint": {"type": "boolean", "description": "Run ktlint", "default": True},
                    "extra_args": {"type": "array", "items": {"type": "string"}, "description": "Extra args", "default": None},
                },
                "required": [],
            },
        }, kotlin_analyze, None, [], False, "🟣", None),

        ("kotlin_format", "language_support", {
            "name": "kotlin_format",
            "description": "Format Kotlin code (ktlint)",
            "parameters": {
                "type": "object",
                "properties": {
                    "repo_path": {"type": "string", "description": "Repository path", "default": "."},
                    "ktlint_format": {"type": "boolean", "description": "Run ktlintFormat", "default": True},
                },
                "required": [],
            },
        }, kotlin_format, None, [], False, "🟣", None),

        # Swift
        ("swift_analyze", "language_support", {
            "name": "swift_analyze",
            "description": "Run Swift analysis (swiftlint, swiftformat, xcodebuild)",
            "parameters": {
                "type": "object",
                "properties": {
                    "repo_path": {"type": "string", "description": "Repository path", "default": "."},
                    "swiftlint": {"type": "boolean", "description": "Run swiftlint", "default": True},
                    "swiftformat_check": {"type": "boolean", "description": "Run swiftformat --lint", "default": True},
                    "xcodebuild": {"type": "boolean", "description": "Run xcodebuild analyze", "default": False},
                    "extra_args": {"type": "array", "items": {"type": "string"}, "description": "Extra args", "default": None},
                },
                "required": [],
            },
        }, swift_analyze, None, [], False, "🍎", None),

        ("swift_format", "language_support", {
            "name": "swift_format",
            "description": "Format Swift code (swiftformat, swiftlint autocorrect)",
            "parameters": {
                "type": "object",
                "properties": {
                    "repo_path": {"type": "string", "description": "Repository path", "default": "."},
                    "swiftformat": {"type": "boolean", "description": "Run swiftformat", "default": True},
                    "swiftlint_autocorrect": {"type": "boolean", "description": "Run swiftlint autocorrect", "default": True},
                },
                "required": [],
            },
        }, swift_format, None, [], False, "🍎", None),

        # C#
        ("csharp_analyze", "language_support", {
            "name": "csharp_analyze",
            "description": "Run C# analysis (dotnet format, roslynator, sonaranalyzer)",
            "parameters": {
                "type": "object",
                "properties": {
                    "repo_path": {"type": "string", "description": "Repository path", "default": "."},
                    "dotnet_format_check": {"type": "boolean", "description": "Run dotnet format --verify-no-changes", "default": True},
                    "roslynator": {"type": "boolean", "description": "Run roslynator", "default": True},
                    "sonaranalyzer": {"type": "boolean", "description": "Run sonaranalyzer", "default": False},
                    "build": {"type": "boolean", "description": "Run dotnet build", "default": True},
                    "extra_args": {"type": "array", "items": {"type": "string"}, "description": "Extra args", "default": None},
                },
                "required": [],
            },
        }, csharp_analyze, None, [], False, "🔷", None),

        ("csharp_format", "language_support", {
            "name": "csharp_format",
            "description": "Format C# code (dotnet format)",
            "parameters": {
                "type": "object",
                "properties": {
                    "repo_path": {"type": "string", "description": "Repository path", "default": "."},
                    "dotnet_format": {"type": "boolean", "description": "Run dotnet format", "default": True},
                },
                "required": [],
            },
        }, csharp_format, None, [], False, "🔷", None),

        # C++
        ("cpp_analyze", "language_support", {
            "name": "cpp_analyze",
            "description": "Run C++ analysis (clang-tidy, cppcheck, clang-format, cmake)",
            "parameters": {
                "type": "object",
                "properties": {
                    "repo_path": {"type": "string", "description": "Repository path", "default": "."},
                    "clang_tidy": {"type": "boolean", "description": "Run clang-tidy", "default": True},
                    "cppcheck": {"type": "boolean", "description": "Run cppcheck", "default": True},
                    "clang_format_check": {"type": "boolean", "description": "Run clang-format --dry-run", "default": True},
                    "cmake": {"type": "boolean", "description": "Build with cmake", "default": False},
                    "extra_args": {"type": "array", "items": {"type": "string"}, "description": "Extra args", "default": None},
                },
                "required": [],
            },
        }, cpp_analyze, None, [], False, "⚙️", None),

        ("cpp_format", "language_support", {
            "name": "cpp_format",
            "description": "Format C++ code (clang-format)",
            "parameters": {
                "type": "object",
                "properties": {
                    "repo_path": {"type": "string", "description": "Repository path", "default": "."},
                    "clang_format": {"type": "boolean", "description": "Run clang-format -i", "default": True},
                },
                "required": [],
            },
        }, cpp_format, None, [], False, "⚙️", None),

        # Dart/Flutter
        ("dart_analyze", "language_support", {
            "name": "dart_analyze",
            "description": "Run Dart/Flutter analysis (dart analyze, dart format, very_good_analysis)",
            "parameters": {
                "type": "object",
                "properties": {
                    "repo_path": {"type": "string", "description": "Repository path", "default": "."},
                    "dart_analyze_cmd": {"type": "boolean", "description": "Run dart analyze", "default": True},
                    "dart_format_check": {"type": "boolean", "description": "Run dart format --check", "default": True},
                    "very_good_analysis": {"type": "boolean", "description": "Run very_good_analysis", "default": False},
                    "extra_args": {"type": "array", "items": {"type": "string"}, "description": "Extra args", "default": None},
                },
                "required": [],
            },
        }, dart_analyze, None, [], False, "💙", None),

        ("dart_format", "language_support", {
            "name": "dart_format",
            "description": "Format Dart code (dart format)",
            "parameters": {
                "type": "object",
                "properties": {
                    "repo_path": {"type": "string", "description": "Repository path", "default": "."},
                    "dart_format_cmd": {"type": "boolean", "description": "Run dart format", "default": True},
                },
                "required": [],
            },
        }, dart_format, None, [], False, "💙", None),

        # Universal
        ("detect_languages", "language_support", {
            "name": "detect_languages",
            "description": "Detect programming languages in a project",
            "parameters": {
                "type": "object",
                "properties": {
                    "repo_path": {"type": "string", "description": "Repository path", "default": "."},
                },
                "required": [],
            },
        }, detect_languages, None, [], False, "🔍", None),

        ("analyze_all", "language_support", {
            "name": "analyze_all",
            "description": "Run analysis for all detected languages in project",
            "parameters": {
                "type": "object",
                "properties": {
                    "repo_path": {"type": "string", "description": "Repository path", "default": "."},
                },
                "required": [],
            },
        }, analyze_all, None, [], False, "🌐", None),
    ]

    for name, toolset, schema, handler, check_fn, requires_env, is_async, emoji, dynamic in tools:
        registry.register(
            name=name,
            toolset=toolset,
            schema=schema,
            handler=handler,
            check_fn=check_fn,
            requires_env=requires_env,
            is_async=is_async,
            description=schema.get("description", ""),
            emoji=emoji,
            max_result_size_chars=50000,
        )


# Auto-register on import
_register_language_tools()

__all__ = [
    "rust_analyze",
    "rust_fmt",
    "python_analyze",
    "python_format",
    "typescript_analyze",
    "typescript_format",
    "go_analyze",
    "go_format",
    "java_analyze",
    "kotlin_analyze",
    "kotlin_format",
    "swift_analyze",
    "swift_format",
    "csharp_analyze",
    "csharp_format",
    "cpp_analyze",
    "cpp_format",
    "dart_analyze",
    "dart_format",
    "detect_languages",
    "analyze_all",
]

if __name__ == "__main__":
    print("Language support tools loaded successfully")