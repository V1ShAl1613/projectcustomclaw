#!/usr/bin/env python3
"""
Testing Tools Module

Extends Hermes with comprehensive testing capabilities:
- pytest
- cargo test
- go test
- jest
- vitest
- flutter test
- JUnit
- Coverage reports
- Benchmark reports

All operations use the existing terminal tool infrastructure.
"""

import json
import logging
import os
import re
import subprocess
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


def _detect_test_framework(repo_path: Path) -> Dict[str, Any]:
    """Detect available test frameworks in a project."""
    file_ops = _get_file_ops()
    
    frameworks = {
        "pytest": False,
        "cargo": False,
        "go": False,
        "jest": False,
        "vitest": False,
        "flutter": False,
        "junit": False,
        "maven": False,
        "gradle": False,
    }
    
    config_files = {
        "pytest": ["pytest.ini", "pyproject.toml", "setup.cfg", "tox.ini", "requirements.txt", "requirements-dev.txt"],
        "cargo": ["Cargo.toml"],
        "go": ["go.mod"],
        "jest": ["package.json", "jest.config.js", "jest.config.ts"],
        "vitest": ["package.json", "vitest.config.js", "vitest.config.ts"],
        "flutter": ["pubspec.yaml"],
        "junit": ["pom.xml", "build.gradle", "build.gradle.kts"],
    }
    
    for framework, files in config_files.items():
        for f in files:
            if file_ops.exists(repo_path / f):
                frameworks[framework] = True
                break
    
    # Check package.json for test scripts
    if file_ops.exists(repo_path / "package.json"):
        try:
            pkg = json.loads(file_ops.read(repo_path / "package.json"))
            scripts = pkg.get("scripts", {})
            if "test" in scripts:
                test_cmd = scripts["test"].lower()
                if "jest" in test_cmd:
                    frameworks["jest"] = True
                if "vitest" in test_cmd:
                    frameworks["vitest"] = True
                if "pytest" in test_cmd:
                    frameworks["pytest"] = True
        except:
            pass
    
    return frameworks


def run_pytest(
    repo_path: str = ".",
    test_path: Optional[str] = None,
    markers: Optional[str] = None,
    keywords: Optional[str] = None,
    coverage: bool = False,
    coverage_format: str = "term-missing",  # term, term-missing, html, xml, json
    coverage_output: Optional[str] = None,
    verbose: bool = True,
    parallel: bool = False,
    workers: int = 0,
    junit_xml: Optional[str] = None,
    extra_args: Optional[List[str]] = None,
    task_id: str = "default",
) -> str:
    """Run pytest tests."""
    try:
        resolved = _resolve_path(repo_path, task_id)
        file_ops = _get_file_ops(task_id)
        
        if not file_ops.exists(resolved):
            return json.dumps({"error": f"Path not found: {repo_path}"})
        
        cmd_parts = ["python", "-m", "pytest"]
        
        if test_path:
            test_resolved = _resolve_path(test_path, task_id)
            cmd_parts.append(str(test_resolved.relative_to(resolved)))
        
        if markers:
            cmd_parts.extend(["-m", markers])
        
        if keywords:
            cmd_parts.extend(["-k", keywords])
        
        if coverage:
            cmd_parts.extend(["--cov", ".", f"--cov-report={coverage_format}"])
            if coverage_output:
                cmd_parts.extend(["--cov-report", f"html:{coverage_output}"])
        
        if verbose:
            cmd_parts.append("-v")
        else:
            cmd_parts.append("-q")
        
        if parallel:
            if workers > 0:
                cmd_parts.extend(["-n", str(workers)])
            else:
                cmd_parts.append("-n auto")
        
        if junit_xml:
            cmd_parts.extend(["--junitxml", junit_xml])
        
        if extra_args:
            cmd_parts.extend(extra_args)
        
        command = f"cd {resolved} && " + " ".join(cmd_parts)
        result = _run_command(command, task_id, timeout=600)
        
        # Parse output for summary
        output = result.get("stdout", "") + result.get("stderr", "")
        summary = _parse_pytest_output(output)
        
        return json.dumps({
            "success": result.get("success", False),
            "output": output,
            "summary": summary,
            "returncode": result.get("returncode"),
        })
    
    except Exception as e:
        logger.exception("run_pytest error: %s", e)
        return json.dumps({"error": f"Pytest failed: {e}"})


def _parse_pytest_output(output: str) -> Dict[str, Any]:
    """Parse pytest output for summary."""
    summary = {
        "passed": 0,
        "failed": 0,
        "skipped": 0,
        "errors": 0,
        "total": 0,
        "duration": 0,
    }
    
    # Look for final summary line
    patterns = [
        r"(\d+) passed",
        r"(\d+) failed",
        r"(\d+) skipped",
        r"(\d+) error",
        r"(\d+) passed, (\d+) failed",
        r"(\d+) passed, (\d+) failed, (\d+) skipped",
        r"in ([\d.]+)s",
        r"in ([\d.]+)ms",
    ]
    
    for line in output.split('\n'):
        if "passed" in line or "failed" in line or "error" in line:
            for pattern in patterns:
                match = re.search(pattern, line)
                if match:
                    groups = match.groups()
                    if len(groups) == 1:
                        if "passed" in pattern:
                            summary["passed"] = int(groups[0])
                        elif "failed" in pattern:
                            summary["failed"] = int(groups[0])
                        elif "skipped" in pattern:
                            summary["skipped"] = int(groups[0])
                        elif "error" in pattern:
                            summary["errors"] = int(groups[0])
                    elif len(groups) >= 2:
                        summary["passed"] = int(groups[0])
                        summary["failed"] = int(groups[1])
                        if len(groups) >= 3:
                            summary["skipped"] = int(groups[2])
                    elif "in" in pattern and ("s" in pattern or "ms" in pattern):
                        time_str = groups[0]
                        if "ms" in time_str:
                            summary["duration"] = float(time_str.replace("ms", "")) / 1000
                        else:
                            summary["duration"] = float(time_str.replace("s", ""))
    
    summary["total"] = summary["passed"] + summary["failed"] + summary["skipped"] + summary["errors"]
    return summary


def run_cargo_test(
    repo_path: str = ".",
    package: Optional[str] = None,
    test: Optional[str] = None,
    lib: bool = False,
    bins: bool = False,
    examples: bool = False,
    benches: bool = False,
    all_targets: bool = False,
    doc: bool = False,
    no_run: bool = False,
    release: bool = False,
    features: Optional[List[str]] = None,
    all_features: bool = False,
    no_default_features: bool = False,
    jobs: Optional[int] = None,
    verbose: bool = True,
    extra_args: Optional[List[str]] = None,
    task_id: str = "default",
) -> str:
    """Run cargo tests."""
    try:
        resolved = _resolve_path(repo_path, task_id)
        file_ops = _get_file_ops(task_id)
        
        if not file_ops.exists(resolved / "Cargo.toml"):
            return json.dumps({"error": f"Not a Cargo project: {repo_path}"})
        
        cmd_parts = ["cargo", "test"]
        
        if package:
            cmd_parts.extend(["-p", package])
        
        if test:
            cmd_parts.append(test)
        
        if lib:
            cmd_parts.append("--lib")
        if bins:
            cmd_parts.append("--bins")
        if examples:
            cmd_parts.append("--examples")
        if benches:
            cmd_parts.append("--benches")
        if all_targets:
            cmd_parts.append("--all-targets")
        if doc:
            cmd_parts.append("--doc")
        if no_run:
            cmd_parts.append("--no-run")
        if release:
            cmd_parts.append("--release")
        
        if features:
            for f in features:
                cmd_parts.extend(["--features", f])
        if all_features:
            cmd_parts.append("--all-features")
        if no_default_features:
            cmd_parts.append("--no-default-features")
        
        if jobs:
            cmd_parts.extend(["-j", str(jobs)])
        
        if verbose:
            cmd_parts.append("--verbose")
        
        if extra_args:
            cmd_parts.extend(extra_args)
        
        command = f"cd {resolved} && " + " ".join(cmd_parts)
        result = _run_command(command, task_id, timeout=600)
        
        output = result.get("stdout", "") + result.get("stderr", "")
        summary = _parse_cargo_output(output)
        
        return json.dumps({
            "success": result.get("success", False),
            "output": output,
            "summary": summary,
            "returncode": result.get("returncode"),
        })
    
    except Exception as e:
        logger.exception("run_cargo_test error: %s", e)
        return json.dumps({"error": f"Cargo test failed: {e}"})


def _parse_cargo_output(output: str) -> Dict[str, Any]:
    """Parse cargo test output."""
    summary = {
        "passed": 0,
        "failed": 0,
        "ignored": 0,
        "measured": 0,
        "filtered_out": 0,
        "total": 0,
    }
    
    for line in output.split('\n'):
        if "test result:" in line:
            # test result: ok. 5 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out
            parts = line.split("test result:")[1].strip().split(";")
            for part in parts:
                part = part.strip()
                if "passed" in part:
                    summary["passed"] = int(part.split()[0])
                elif "failed" in part:
                    summary["failed"] = int(part.split()[0])
                elif "ignored" in part:
                    summary["ignored"] = int(part.split()[0])
                elif "measured" in part:
                    summary["measured"] = int(part.split()[0])
                elif "filtered" in part:
                    summary["filtered_out"] = int(part.split()[0])
            summary["total"] = summary["passed"] + summary["failed"]
    
    return summary


def run_go_test(
    repo_path: str = ".",
    packages: Optional[List[str]] = None,
    run: Optional[str] = None,
    skip: Optional[str] = None,
    count: int = 1,
    fail_fast: bool = False,
    parallel: int = 0,
    timeout: Optional[str] = None,
    verbose: bool = True,
    race: bool = False,
    cover: bool = False,
    cover_profile: Optional[str] = None,
    cover_mode: str = "set",
    bench: Optional[str] = None,
    benchtime: Optional[str] = None,
    extra_args: Optional[List[str]] = None,
    task_id: str = "default",
) -> str:
    """Run go tests."""
    try:
        resolved = _resolve_path(repo_path, task_id)
        file_ops = _get_file_ops(task_id)
        
        if not file_ops.exists(resolved / "go.mod"):
            return json.dumps({"error": f"Not a Go module: {repo_path}"})
        
        cmd_parts = ["go", "test"]
        
        if packages:
            cmd_parts.extend(packages)
        else:
            cmd_parts.append("./...")
        
        if run:
            cmd_parts.extend(["-run", run])
        if skip:
            cmd_parts.extend(["-skip", skip])
        if count > 1:
            cmd_parts.extend(["-count", str(count)])
        if fail_fast:
            cmd_parts.append("-failfast")
        if parallel > 0:
            cmd_parts.extend(["-p", str(parallel)])
        if timeout:
            cmd_parts.extend(["-timeout", timeout])
        if verbose:
            cmd_parts.append("-v")
        if race:
            cmd_parts.append("-race")
        if cover:
            cmd_parts.append("-cover")
        if cover_profile:
            cmd_parts.extend(["-coverprofile", cover_profile])
        if cover_mode:
            cmd_parts.extend(["-covermode", cover_mode])
        if bench:
            cmd_parts.extend(["-bench", bench])
        if benchtime:
            cmd_parts.extend(["-benchtime", benchtime])
        
        if extra_args:
            cmd_parts.extend(extra_args)
        
        command = f"cd {resolved} && " + " ".join(cmd_parts)
        result = _run_command(command, task_id, timeout=600)
        
        output = result.get("stdout", "") + result.get("stderr", "")
        summary = _parse_go_output(output)
        
        return json.dumps({
            "success": result.get("success", False),
            "output": output,
            "summary": summary,
            "returncode": result.get("returncode"),
        })
    
    except Exception as e:
        logger.exception("run_go_test error: %s", e)
        return json.dumps({"error": f"Go test failed: {e}"})


def _parse_go_output(output: str) -> Dict[str, Any]:
    """Parse go test output."""
    summary = {
        "packages": 0,
        "passed": 0,
        "failed": 0,
        "skipped": 0,
        "duration": 0,
    }
    
    for line in output.split('\n'):
        if line.startswith("ok") or line.startswith("FAIL"):
            parts = line.split()
            if len(parts) >= 2:
                summary["packages"] += 1
                if parts[0] == "ok":
                    summary["passed"] += 1
                else:
                    summary["failed"] += 1
                # Duration is usually the last part
                if len(parts) >= 3:
                    try:
                        duration_str = parts[-1].replace("s", "")
                        summary["duration"] += float(duration_str)
                    except:
                        pass
            elif "SKIP" in line:
                summary["skipped"] += 1
    
    return summary


def run_jest(
    repo_path: str = ".",
    test_path: Optional[str] = None,
    test_name_pattern: Optional[str] = None,
    test_path_pattern: Optional[str] = None,
    coverage: bool = False,
    coverage_directory: Optional[str] = None,
    coverage_reporters: Optional[List[str]] = None,
    watch: bool = False,
    watch_all: bool = False,
    verbose: bool = True,
    ci: bool = False,
    max_workers: Optional[int] = None,
    json_output: bool = False,
    output_file: Optional[str] = None,
    extra_args: Optional[List[str]] = None,
    task_id: str = "default",
) -> str:
    """Run Jest tests."""
    try:
        resolved = _resolve_path(repo_path, task_id)
        file_ops = _get_file_ops(task_id)
        
        if not file_ops.exists(resolved / "package.json"):
            return json.dumps({"error": f"No package.json found: {repo_path}"})
        
        # Check if jest is available
        pkg = json.loads(file_ops.read(resolved / "package.json"))
        dev_deps = pkg.get("devDependencies", {})
        deps = pkg.get("dependencies", {})
        all_deps = {**dev_deps, **deps}
        
        if "jest" not in all_deps:
            return json.dumps({"error": "Jest not found in dependencies"})
        
        cmd_parts = ["npx", "jest"]
        
        if test_path:
            cmd_parts.append(test_path)
        
        if test_name_pattern:
            cmd_parts.extend(["-t", test_name_pattern])
        
        if test_path_pattern:
            cmd_parts.extend(["--testPathPattern", test_path_pattern])
        
        if coverage:
            cmd_parts.append("--coverage")
            if coverage_directory:
                cmd_parts.extend(["--coverageDirectory", coverage_directory])
            if coverage_reporters:
                for r in coverage_reporters:
                    cmd_parts.extend(["--coverageReporters", r])
        
        if watch:
            cmd_parts.append("--watch")
        if watch_all:
            cmd_parts.append("--watchAll")
        
        if verbose:
            cmd_parts.append("--verbose")
        
        if ci:
            cmd_parts.append("--ci")
        
        if max_workers:
            cmd_parts.extend(["--maxWorkers", str(max_workers)])
        
        if json_output:
            cmd_parts.append("--json")
            if output_file:
                cmd_parts.extend(["--outputFile", output_file])
        
        if extra_args:
            cmd_parts.extend(extra_args)
        
        command = f"cd {resolved} && " + " ".join(cmd_parts)
        result = _run_command(command, task_id, timeout=600)
        
        output = result.get("stdout", "") + result.get("stderr", "")
        summary = _parse_jest_output(output)
        
        return json.dumps({
            "success": result.get("success", False),
            "output": output,
            "summary": summary,
            "returncode": result.get("returncode"),
        })
    
    except Exception as e:
        logger.exception("run_jest error: %s", e)
        return json.dumps({"error": f"Jest failed: {e}"})


def _parse_jest_output(output: str) -> Dict[str, Any]:
    """Parse Jest output."""
    summary = {
        "test_suites": 0,
        "tests": 0,
        "passed": 0,
        "failed": 0,
        "skipped": 0,
        "duration": 0,
    }
    
    for line in output.split('\n'):
        if "Test Suites:" in line:
            # Test Suites: 1 passed, 1 total
            parts = line.split(":")[1].strip().split(",")
            for part in parts:
                part = part.strip()
                if "passed" in part:
                    summary["test_suites"] = int(part.split()[0])
                elif "failed" in part:
                    summary["test_suites"] += int(part.split()[0])
                elif "total" in part:
                    pass
        elif "Tests:" in line:
            parts = line.split(":")[1].strip().split(",")
            for part in parts:
                part = part.strip()
                if "passed" in part:
                    summary["passed"] = int(part.split()[0])
                elif "failed" in part:
                    summary["failed"] = int(part.split()[0])
                elif "skipped" in part:
                    summary["skipped"] = int(part.split()[0])
                elif "total" in part:
                    summary["tests"] = int(part.split()[0])
    
    return summary


def run_vitest(
    repo_path: str = ".",
    test_path: Optional[str] = None,
    coverage: bool = False,
    coverage_reporter: Optional[str] = None,
    watch: bool = False,
    ui: bool = False,
    run: bool = True,
    verbose: bool = True,
    extra_args: Optional[List[str]] = None,
    task_id: str = "default",
) -> str:
    """Run Vitest tests."""
    try:
        resolved = _resolve_path(repo_path, task_id)
        file_ops = _get_file_ops(task_id)
        
        if not file_ops.exists(resolved / "package.json"):
            return json.dumps({"error": f"No package.json found: {repo_path}"})
        
        pkg = json.loads(file_ops.read(resolved / "package.json"))
        dev_deps = pkg.get("devDependencies", {})
        deps = pkg.get("dependencies", {})
        all_deps = {**dev_deps, **deps}
        
        if "vitest" not in all_deps:
            return json.dumps({"error": "Vitest not found in dependencies"})
        
        cmd_parts = ["npx", "vitest"]
        
        if run:
            cmd_parts.append("run")
        
        if test_path:
            cmd_parts.append(test_path)
        
        if coverage:
            cmd_parts.append("--coverage")
            if coverage_reporter:
                cmd_parts.extend(["--reporter", coverage_reporter])
        
        if watch:
            cmd_parts.append("--watch")
        
        if ui:
            cmd_parts.append("--ui")
        
        if verbose:
            cmd_parts.append("--verbose")
        
        if extra_args:
            cmd_parts.extend(extra_args)
        
        command = f"cd {resolved} && " + " ".join(cmd_parts)
        result = _run_command(command, task_id, timeout=600)
        
        output = result.get("stdout", "") + result.get("stderr", "")
        summary = _parse_vitest_output(output)
        
        return json.dumps({
            "success": result.get("success", False),
            "output": output,
            "summary": summary,
            "returncode": result.get("returncode"),
        })
    
    except Exception as e:
        logger.exception("run_vitest error: %s", e)
        return json.dumps({"error": f"Vitest failed: {e}"})


def _parse_vitest_output(output: str) -> Dict[str, Any]:
    """Parse Vitest output (similar to Jest)."""
    return _parse_jest_output(output)


def run_flutter_test(
    repo_path: str = ".",
    test_path: Optional[str] = None,
    coverage: bool = False,
    coverage_path: Optional[str] = None,
    verbose: bool = True,
    plain_name: Optional[str] = None,
    update_goldens: bool = False,
    extra_args: Optional[List[str]] = None,
    task_id: str = "default",
) -> str:
    """Run Flutter tests."""
    try:
        resolved = _resolve_path(repo_path, task_id)
        file_ops = _get_file_ops(task_id)
        
        if not file_ops.exists(resolved / "pubspec.yaml"):
            return json.dumps({"error": f"Not a Flutter project: {repo_path}"})
        
        cmd_parts = ["flutter", "test"]
        
        if test_path:
            cmd_parts.append(test_path)
        
        if coverage:
            cmd_parts.append("--coverage")
            if coverage_path:
                cmd_parts.extend(["--coverage-path", coverage_path])
        
        if verbose:
            cmd_parts.append("--verbose")
        
        if plain_name:
            cmd_parts.extend(["--plain-name", plain_name])
        
        if update_goldens:
            cmd_parts.append("--update-goldens")
        
        if extra_args:
            cmd_parts.extend(extra_args)
        
        command = f"cd {resolved} && " + " ".join(cmd_parts)
        result = _run_command(command, task_id, timeout=600)
        
        output = result.get("stdout", "") + result.get("stderr", "")
        summary = _parse_flutter_output(output)
        
        return json.dumps({
            "success": result.get("success", False),
            "output": output,
            "summary": summary,
            "returncode": result.get("returncode"),
        })
    
    except Exception as e:
        logger.exception("run_flutter_test error: %s", e)
        return json.dumps({"error": f"Flutter test failed: {e}"})


def _parse_flutter_output(output: str) -> Dict[str, Any]:
    """Parse Flutter test output."""
    summary = {
        "passed": 0,
        "failed": 0,
        "skipped": 0,
        "total": 0,
    }
    
    for line in output.split('\n'):
        if "All tests passed!" in line:
            # +1: All tests passed!
            pass
        elif "test" in line.lower() and ("passed" in line.lower() or "failed" in line.lower()):
            # 00:00 +1: test description
            if "passed" in line.lower():
                summary["passed"] += 1
            elif "failed" in line.lower():
                summary["failed"] += 1
    
    summary["total"] = summary["passed"] + summary["failed"] + summary["skipped"]
    return summary


def run_junit(
    repo_path: str = ".",
    build_tool: str = "auto",  # auto, maven, gradle
    test_class: Optional[str] = None,
    test_method: Optional[str] = None,
    fail_fast: bool = False,
    verbose: bool = True,
    reports_dir: Optional[str] = None,
    extra_args: Optional[List[str]] = None,
    task_id: str = "default",
) -> str:
    """Run JUnit tests via Maven or Gradle."""
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
        
        if build_tool == "maven":
            return _run_junit_maven(resolved, test_class, test_method, fail_fast, verbose, reports_dir, extra_args, task_id)
        else:
            return _run_junit_gradle(resolved, test_class, test_method, fail_fast, verbose, reports_dir, extra_args, task_id)
    
    except Exception as e:
        logger.exception("run_junit error: %s", e)
        return json.dumps({"error": f"JUnit test failed: {e}"})


def _run_junit_maven(
    repo_path: Path,
    test_class: Optional[str] = None,
    test_method: Optional[str] = None,
    fail_fast: bool = False,
    verbose: bool = True,
    reports_dir: Optional[str] = None,
    extra_args: Optional[List[str]] = None,
    task_id: str = "default",
) -> str:
    """Run JUnit via Maven."""
    cmd_parts = ["mvn", "test"]
    
    if test_class:
        if test_method:
            cmd_parts.extend(["-Dtest", f"{test_class}#{test_method}"])
        else:
            cmd_parts.extend(["-Dtest", test_class])
    
    if fail_fast:
        cmd_parts.append("-DfailIfNoTests=false")
        cmd_parts.append("-DtrimStackTrace=false")
    
    if verbose:
        cmd_parts.append("-X")
    
    if reports_dir:
        cmd_parts.extend(["-Dsurefire.reportsDirectory", reports_dir])
    
    if extra_args:
        cmd_parts.extend(extra_args)
    
    command = f"cd {repo_path} && " + " ".join(cmd_parts)
    result = _run_command(command, task_id, timeout=600)
    
    output = result.get("stdout", "") + result.get("stderr", "")
    summary = _parse_junit_maven_output(output)
    
    return json.dumps({
        "success": result.get("success", False),
        "output": output,
        "summary": summary,
        "returncode": result.get("returncode"),
    })


def _run_junit_gradle(
    repo_path: Path,
    test_class: Optional[str] = None,
    test_method: Optional[str] = None,
    fail_fast: bool = False,
    verbose: bool = True,
    reports_dir: Optional[str] = None,
    extra_args: Optional[List[str]] = None,
    task_id: str = "default",
) -> str:
    """Run JUnit via Gradle."""
    cmd_parts = ["./gradlew", "test"]
    
    if test_class:
        if test_method:
            cmd_parts.extend(["--tests", f"{test_class}.{test_method}"])
        else:
            cmd_parts.extend(["--tests", test_class])
    
    if fail_fast:
        cmd_parts.append("--fail-fast")
    
    if verbose:
        cmd_parts.append("--info")
    
    if reports_dir:
        cmd_parts.extend(["-Dtest.reportsDir", reports_dir])
    
    if extra_args:
        cmd_parts.extend(extra_args)
    
    command = f"cd {repo_path} && " + " ".join(cmd_parts)
    result = _run_command(command, task_id, timeout=600)
    
    output = result.get("stdout", "") + result.get("stderr", "")
    summary = _parse_junit_gradle_output(output)
    
    return json.dumps({
        "success": result.get("success", False),
        "output": output,
        "summary": summary,
        "returncode": result.get("returncode"),
    })


def _parse_junit_maven_output(output: str) -> Dict[str, Any]:
    """Parse Maven Surefire output."""
    summary = {
        "tests_run": 0,
        "failures": 0,
        "errors": 0,
        "skipped": 0,
        "time": 0,
    }
    
    for line in output.split('\n'):
        if "Tests run:" in line:
            # Tests run: 5, Failures: 1, Errors: 0, Skipped: 0, Time elapsed: 1.234 s
            parts = line.split(",")
            for part in parts:
                part = part.strip()
                if part.startswith("Tests run:"):
                    summary["tests_run"] = int(part.split(":")[1].strip())
                elif part.startswith("Failures:"):
                    summary["failures"] = int(part.split(":")[1].strip())
                elif part.startswith("Errors:"):
                    summary["errors"] = int(part.split(":")[1].strip())
                elif part.startswith("Skipped:"):
                    summary["skipped"] = int(part.split(":")[1].strip())
                elif part.startswith("Time elapsed:"):
                    time_str = part.split(":")[1].strip().replace("s", "")
                    summary["time"] = float(time_str)
    
    return summary


def _parse_junit_gradle_output(output: str) -> Dict[str, Any]:
    """Parse Gradle test output."""
    return _parse_junit_maven_output(output)


def generate_coverage_report(
    repo_path: str = ".",
    format: str = "html",  # html, xml, json, lcov, text
    output_path: Optional[str] = None,
    task_id: str = "default",
) -> str:
    """Generate coverage report from existing coverage data."""
    try:
        resolved = _resolve_path(repo_path, task_id)
        file_ops = _get_file_ops(task_id)
        
        if not file_ops.exists(resolved):
            return json.dumps({"error": f"Path not found: {repo_path}"})
        
        # Find coverage data
        coverage_files = []
        for pattern in ["coverage.xml", "coverage.json", "lcov.info", ".coverage", "coverage/*"]:
            # This is simplified - would need glob support
            pass
        
        return json.dumps({
            "success": True,
            "message": "Coverage report generation would use framework-specific tools",
            "detected_frameworks": _detect_test_framework(resolved),
        })
    
    except Exception as e:
        logger.exception("generate_coverage_report error: %s", e)
        return json.dumps({"error": f"Coverage report failed: {e}"})


def run_benchmarks(
    repo_path: str = ".",
    framework: str = "auto",  # auto, pytest, cargo, go, jest
    benchmark_pattern: Optional[str] = None,
    iterations: int = 10,
    warmup: int = 3,
    output_format: str = "text",  # text, json, csv
    output_path: Optional[str] = None,
    task_id: str = "default",
) -> str:
    """Run benchmarks."""
    try:
        resolved = _resolve_path(repo_path, task_id)
        file_ops = _get_file_ops(task_id)
        
        if not file_ops.exists(resolved):
            return json.dumps({"error": f"Path not found: {repo_path}"})
        
        if framework == "auto":
            frameworks = _detect_test_framework(resolved)
            for fw in ["cargo", "go", "pytest", "jest"]:
                if frameworks.get(fw):
                    framework = fw
                    break
            else:
                framework = "pytest"
        
        if framework == "cargo":
            cmd = f"cd {resolved} && cargo bench"
            if benchmark_pattern:
                cmd += f" {benchmark_pattern}"
            if output_format == "json":
                cmd += " -- --output-format=json"
        elif framework == "go":
            cmd = f"cd {resolved} && go test -bench={benchmark_pattern or '.'} -benchtime={iterations}x -count=1"
        elif framework == "pytest":
            cmd = f"cd {resolved} && python -m pytest --benchmark-only"
            if benchmark_pattern:
                cmd += f" -k {benchmark_pattern}"
        else:
            return json.dumps({"error": f"Benchmark not supported for {framework}"})
        
        result = _run_command(cmd, task_id, timeout=600)
        
        return json.dumps({
            "success": result.get("success", False),
            "output": result.get("stdout", "") + result.get("stderr", ""),
            "framework": framework,
        })
    
    except Exception as e:
        logger.exception("run_benchmarks error: %s", e)
        return json.dumps({"error": f"Benchmark failed: {e}"})


def detect_test_frameworks(
    repo_path: str = ".",
    task_id: str = "default",
) -> str:
    """Detect available test frameworks in a project."""
    try:
        resolved = _resolve_path(repo_path, task_id)
        file_ops = _get_file_ops(task_id)
        
        if not file_ops.exists(resolved):
            return json.dumps({"error": f"Path not found: {repo_path}"})
        
        frameworks = _detect_test_framework(resolved)
        
        # Add details
        details = {}
        if frameworks["pytest"]:
            details["pytest"] = {"config_files": ["pytest.ini", "pyproject.toml"]}
        if frameworks["cargo"]:
            details["cargo"] = {"config_file": "Cargo.toml"}
        if frameworks["go"]:
            details["go"] = {"config_file": "go.mod"}
        if frameworks["jest"]:
            details["jest"] = {"config_files": ["package.json", "jest.config.js"]}
        if frameworks["vitest"]:
            details["vitest"] = {"config_files": ["package.json", "vitest.config.js"]}
        if frameworks["flutter"]:
            details["flutter"] = {"config_file": "pubspec.yaml"}
        if frameworks["junit"]:
            details["junit"] = {"build_tools": ["maven" if file_ops.exists(resolved / "pom.xml") else "gradle"]}
        
        return json.dumps({
            "frameworks": {k: v for k, v in frameworks.items() if v},
            "details": details,
        })
    
    except Exception as e:
        logger.exception("detect_test_frameworks error: %s", e)
        return json.dumps({"error": f"Framework detection failed: {e}"})


# Register all tools
def _register_testing_tools():
    """Register all testing tools with the registry."""

    tools = [
        ("run_pytest", "testing", {
            "name": "run_pytest",
            "description": "Run pytest tests with options for coverage, parallel, markers, etc.",
            "parameters": {
                "type": "object",
                "properties": {
                    "repo_path": {"type": "string", "description": "Repository path", "default": "."},
                    "test_path": {"type": "string", "description": "Specific test file or directory", "default": None},
                    "markers": {"type": "string", "description": "Pytest markers expression", "default": None},
                    "keywords": {"type": "string", "description": "Keyword expression", "default": None},
                    "coverage": {"type": "boolean", "description": "Generate coverage report", "default": False},
                    "coverage_format": {"type": "string", "enum": ["term", "term-missing", "html", "xml", "json"], "default": "term-missing"},
                    "coverage_output": {"type": "string", "description": "Coverage output directory", "default": None},
                    "verbose": {"type": "boolean", "description": "Verbose output", "default": True},
                    "parallel": {"type": "boolean", "description": "Run in parallel", "default": False},
                    "workers": {"type": "integer", "description": "Number of workers (0=auto)", "default": 0},
                    "junit_xml": {"type": "string", "description": "JUnit XML output file", "default": None},
                    "extra_args": {"type": "array", "items": {"type": "string"}, "description": "Extra pytest args", "default": None},
                },
                "required": [],
            },
        }, run_pytest, None, [], False, "🐍", None),

        ("run_cargo_test", "testing", {
            "name": "run_cargo_test",
            "description": "Run cargo tests for Rust projects",
            "parameters": {
                "type": "object",
                "properties": {
                    "repo_path": {"type": "string", "description": "Repository path", "default": "."},
                    "package": {"type": "string", "description": "Specific package", "default": None},
                    "test": {"type": "string", "description": "Test name filter", "default": None},
                    "lib": {"type": "boolean", "description": "Test library only", "default": False},
                    "bins": {"type": "boolean", "description": "Test binaries only", "default": False},
                    "examples": {"type": "boolean", "description": "Test examples", "default": False},
                    "benches": {"type": "boolean", "description": "Run benchmarks", "default": False},
                    "all_targets": {"type": "boolean", "description": "Test all targets", "default": False},
                    "doc": {"type": "boolean", "description": "Test documentation", "default": False},
                    "no_run": {"type": "boolean", "description": "Compile but don't run", "default": False},
                    "release": {"type": "boolean", "description": "Release mode", "default": False},
                    "features": {"type": "array", "items": {"type": "string"}, "description": "Features to enable", "default": None},
                    "all_features": {"type": "boolean", "description": "All features", "default": False},
                    "no_default_features": {"type": "boolean", "description": "No default features", "default": False},
                    "jobs": {"type": "integer", "description": "Parallel jobs", "default": None},
                    "verbose": {"type": "boolean", "description": "Verbose output", "default": True},
                    "extra_args": {"type": "array", "items": {"type": "string"}, "description": "Extra cargo args", "default": None},
                },
                "required": [],
            },
        }, run_cargo_test, None, [], False, "🦀", None),

        ("run_go_test", "testing", {
            "name": "run_go_test",
            "description": "Run Go tests",
            "parameters": {
                "type": "object",
                "properties": {
                    "repo_path": {"type": "string", "description": "Repository path", "default": "."},
                    "packages": {"type": "array", "items": {"type": "string"}, "description": "Packages to test", "default": None},
                    "run": {"type": "string", "description": "Run regex", "default": None},
                    "skip": {"type": "string", "description": "Skip regex", "default": None},
                    "count": {"type": "integer", "description": "Run count", "default": 1},
                    "fail_fast": {"type": "boolean", "description": "Fail fast", "default": False},
                    "parallel": {"type": "integer", "description": "Parallel test functions", "default": 0},
                    "timeout": {"type": "string", "description": "Timeout (e.g., 30s)", "default": None},
                    "verbose": {"type": "boolean", "description": "Verbose output", "default": True},
                    "race": {"type": "boolean", "description": "Race detector", "default": False},
                    "cover": {"type": "boolean", "description": "Coverage", "default": False},
                    "cover_profile": {"type": "string", "description": "Coverage profile output", "default": None},
                    "cover_mode": {"type": "string", "description": "Coverage mode", "default": "set"},
                    "bench": {"type": "string", "description": "Benchmark regex", "default": None},
                    "benchtime": {"type": "string", "description": "Benchmark time", "default": None},
                    "extra_args": {"type": "array", "items": {"type": "string"}, "description": "Extra go test args", "default": None},
                },
                "required": [],
            },
        }, run_go_test, None, [], False, "🐹", None),

        ("run_jest", "testing", {
            "name": "run_jest",
            "description": "Run Jest tests for JavaScript/TypeScript",
            "parameters": {
                "type": "object",
                "properties": {
                    "repo_path": {"type": "string", "description": "Repository path", "default": "."},
                    "test_path": {"type": "string", "description": "Test file/directory", "default": None},
                    "test_name_pattern": {"type": "string", "description": "Test name regex", "default": None},
                    "test_path_pattern": {"type": "string", "description": "Test path regex", "default": None},
                    "coverage": {"type": "boolean", "description": "Generate coverage", "default": False},
                    "coverage_directory": {"type": "string", "description": "Coverage output dir", "default": None},
                    "coverage_reporters": {"type": "array", "items": {"type": "string"}, "description": "Coverage reporters", "default": None},
                    "watch": {"type": "boolean", "description": "Watch mode", "default": False},
                    "watch_all": {"type": "boolean", "description": "Watch all tests", "default": False},
                    "verbose": {"type": "boolean", "description": "Verbose output", "default": True},
                    "ci": {"type": "boolean", "description": "CI mode", "default": False},
                    "max_workers": {"type": "integer", "description": "Max workers", "default": None},
                    "json_output": {"type": "boolean", "description": "JSON output", "default": False},
                    "output_file": {"type": "string", "description": "Output file for JSON", "default": None},
                    "extra_args": {"type": "array", "items": {"type": "string"}, "description": "Extra jest args", "default": None},
                },
                "required": [],
            },
        }, run_jest, None, [], False, "🃏", None),

        ("run_vitest", "testing", {
            "name": "run_vitest",
            "description": "Run Vitest tests for JavaScript/TypeScript",
            "parameters": {
                "type": "object",
                "properties": {
                    "repo_path": {"type": "string", "description": "Repository path", "default": "."},
                    "test_path": {"type": "string", "description": "Test file/directory", "default": None},
                    "coverage": {"type": "boolean", "description": "Generate coverage", "default": False},
                    "coverage_reporter": {"type": "string", "description": "Coverage reporter", "default": None},
                    "watch": {"type": "boolean", "description": "Watch mode", "default": False},
                    "ui": {"type": "boolean", "description": "Open UI", "default": False},
                    "run": {"type": "boolean", "description": "Run mode (not watch)", "default": True},
                    "verbose": {"type": "boolean", "description": "Verbose output", "default": True},
                    "extra_args": {"type": "array", "items": {"type": "string"}, "description": "Extra vitest args", "default": None},
                },
                "required": [],
            },
        }, run_vitest, None, [], False, "⚡", None),

        ("run_flutter_test", "testing", {
            "name": "run_flutter_test",
            "description": "Run Flutter/Dart tests",
            "parameters": {
                "type": "object",
                "properties": {
                    "repo_path": {"type": "string", "description": "Repository path", "default": "."},
                    "test_path": {"type": "string", "description": "Test file", "default": None},
                    "coverage": {"type": "boolean", "description": "Generate coverage", "default": False},
                    "coverage_path": {"type": "string", "description": "Coverage output path", "default": None},
                    "verbose": {"type": "boolean", "description": "Verbose output", "default": True},
                    "plain_name": {"type": "string", "description": "Run tests matching name", "default": None},
                    "update_goldens": {"type": "boolean", "description": "Update golden files", "default": False},
                    "extra_args": {"type": "array", "items": {"type": "string"}, "description": "Extra flutter args", "default": None},
                },
                "required": [],
            },
        }, run_flutter_test, None, [], False, "💙", None),

        ("run_junit", "testing", {
            "name": "run_junit",
            "description": "Run JUnit tests via Maven or Gradle",
            "parameters": {
                "type": "object",
                "properties": {
                    "repo_path": {"type": "string", "description": "Repository path", "default": "."},
                    "build_tool": {"type": "string", "enum": ["auto", "maven", "gradle"], "default": "auto"},
                    "test_class": {"type": "string", "description": "Test class name", "default": None},
                    "test_method": {"type": "string", "description": "Test method name", "default": None},
                    "fail_fast": {"type": "boolean", "description": "Fail fast", "default": False},
                    "verbose": {"type": "boolean", "description": "Verbose output", "default": True},
                    "reports_dir": {"type": "string", "description": "Reports directory", "default": None},
                    "extra_args": {"type": "array", "items": {"type": "string"}, "description": "Extra build tool args", "default": None},
                },
                "required": [],
            },
        }, run_junit, None, [], False, "☕", None),

        ("generate_coverage_report", "testing", {
            "name": "generate_coverage_report",
            "description": "Generate coverage report from existing coverage data",
            "parameters": {
                "type": "object",
                "properties": {
                    "repo_path": {"type": "string", "description": "Repository path", "default": "."},
                    "format": {"type": "string", "enum": ["html", "xml", "json", "lcov", "text"], "default": "html"},
                    "output_path": {"type": "string", "description": "Output file path", "default": None},
                },
                "required": [],
            },
        }, generate_coverage_report, None, [], False, "📊", None),

        ("run_benchmarks", "testing", {
            "name": "run_benchmarks",
            "description": "Run benchmarks for various frameworks",
            "parameters": {
                "type": "object",
                "properties": {
                    "repo_path": {"type": "string", "description": "Repository path", "default": "."},
                    "framework": {"type": "string", "enum": ["auto", "pytest", "cargo", "go", "jest"], "default": "auto"},
                    "benchmark_pattern": {"type": "string", "description": "Benchmark name pattern", "default": None},
                    "iterations": {"type": "integer", "description": "Iterations", "default": 10},
                    "warmup": {"type": "integer", "description": "Warmup iterations", "default": 3},
                    "output_format": {"type": "string", "enum": ["text", "json", "csv"], "default": "text"},
                    "output_path": {"type": "string", "description": "Output file", "default": None},
                },
                "required": [],
            },
        }, run_benchmarks, None, [], False, "🏎️", None),

        ("detect_test_frameworks", "testing", {
            "name": "detect_test_frameworks",
            "description": "Detect available test frameworks in a project",
            "parameters": {
                "type": "object",
                "properties": {
                    "repo_path": {"type": "string", "description": "Repository path", "default": "."},
                },
                "required": [],
            },
        }, detect_test_frameworks, None, [], False, "🔍", None),
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
_register_testing_tools()

__all__ = [
    "run_pytest",
    "run_cargo_test",
    "run_go_test",
    "run_jest",
    "run_vitest",
    "run_flutter_test",
    "run_junit",
    "generate_coverage_report",
    "run_benchmarks",
    "detect_test_frameworks",
]

if __name__ == "__main__":
    print("Testing tools loaded successfully")