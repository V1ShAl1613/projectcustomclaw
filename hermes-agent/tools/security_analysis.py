#!/usr/bin/env python3
"""
Security Analysis Tools Module

Provides comprehensive security analysis capabilities:
- Vulnerability scanning (dependencies, containers)
- Secret detection
- Static analysis (bandit, semgrep)
- Misconfiguration detection
- License compliance checking
- SBOM generation (SPDX, CycloneDX)
- Security report generation

All operations are DEFENSIVE ONLY - no exploit generation.
"""

import json
import logging
import os
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

from tools.registry import registry
from tools.file_tools import _resolve_path_for_task, _get_file_ops
from tools.terminal_tool import terminal_tool

logger = logging.getLogger(__name__)


# Secret patterns for detection
SECRET_PATTERNS = {
    "aws_access_key": r"AKIA[0-9A-Z]{16}",
    "aws_secret_key": r"[A-Za-z0-9/+=]{40}",
    "github_token": r"gh[pousr]_[A-Za-z0-9]{36}",
    "gitlab_token": r"glpat-[A-Za-z0-9_-]{20}",
    "slack_token": r"xox[baprs]-[A-Za-z0-9-]{10,}",
    "stripe_key": r"sk_live_[A-Za-z0-9]{24}",
    "sendgrid_key": r"SG\.[A-Za-z0-9_-]{22}\.[A-Za-z0-9_-]{43}",
    "twilio_sid": r"AC[A-Za-z0-9]{32}",
    "twilio_token": r"[A-Za-z0-9]{32}",
    "private_key": r"-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----",
    "ssh_key": r"ssh-(rsa|dss|ed25519) [A-Za-z0-9+/]+[=]{0,3}",
    "generic_api_key": r"[aA][pP][iI][_-]?[kK][eE][yY][_-]?[=:]\s*[A-Za-z0-9_-]{20,}",
    "generic_secret": r"[sS][eE][cC][rR][eE][tT][_-]?[=:]\s*[A-Za-z0-9_-]{20,}",
    "password": r"[pP][aA][sS][sS][wW][oO][rR][dD][_-]?[=:]\s*[^\s]{8,}",
    "jwt": r"eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+",
    "database_url": r"(postgres|mysql|mongodb)://[^:\s]+:[^@\s]+@[^/\s]+",
}


def _run_command(command: str, cwd: Optional[str] = None, timeout: int = 300) -> Dict[str, Any]:
    """Run a shell command and return result."""
    try:
        result = subprocess.run(
            command,
            shell=True,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return {
            "success": result.returncode == 0,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "returncode": result.returncode,
        }
    except subprocess.TimeoutExpired:
        return {"success": False, "error": "Command timed out", "returncode": -1}
    except Exception as e:
        return {"success": False, "error": str(e), "returncode": -1}


def _resolve_path(path: str, task_id: str = "default") -> Path:
    """Resolve a path using Hermes path resolution."""
    return _resolve_path_for_task(path, task_id)


def scan_vulnerabilities(
    path: str = ".",
    scanner: str = "auto",
    format: str = "json",
    severity: str = "medium",
    task_id: str = "default",
) -> str:
    """Scan for vulnerabilities in dependencies.
    
    Args:
        path: Path to scan (default: current directory)
        scanner: Scanner to use (auto, pip-audit, npm-audit, cargo-audit, trivy, grype, osv)
        format: Output format (json, table, sarif)
        severity: Minimum severity (low, medium, high, critical)
        task_id: Task identifier
        
    Returns:
        JSON with vulnerability results
    """
    resolved = _resolve_path(path, task_id)
    
    results = {
        "path": str(resolved),
        "scanner": scanner,
        "vulnerabilities": [],
        "summary": {"critical": 0, "high": 0, "medium": 0, "low": 0},
    }
    
    try:
        # Detect project type and run appropriate scanner
        if scanner in ("auto", "pip-audit"):
            # Python
            req_files = list(resolved.rglob("requirements*.txt")) + list(resolved.rglob("pyproject.toml")) + list(resolved.rglob("Pipfile"))
            if req_files:
                cmd = f"pip-audit --format {format} --desc"
                if severity != "low":
                    cmd += f" --min-severity {severity}"
                result = _run_command(cmd, cwd=str(resolved))
                if result["success"]:
                    try:
                        data = json.loads(result["stdout"])
                        if isinstance(data, dict) and "vulnerabilities" in data:
                            results["vulnerabilities"].extend(data["vulnerabilities"])
                    except Exception:
                        pass
        
        if scanner in ("auto", "npm-audit"):
            # Node.js
            if (resolved / "package.json").exists():
                cmd = f"npm audit --json --audit-level={severity}"
                result = _run_command(cmd, cwd=str(resolved))
                if result["success"]:
                    try:
                        data = json.loads(result["stdout"])
                        if "vulnerabilities" in data:
                            for name, vuln in data["vulnerabilities"].items():
                                vuln["package"] = name
                                results["vulnerabilities"].append(vuln)
                    except Exception:
                        pass
        
        if scanner in ("auto", "cargo-audit"):
            # Rust
            if (resolved / "Cargo.toml").exists():
                cmd = f"cargo audit --json"
                result = _run_command(cmd, cwd=str(resolved))
                if result["success"]:
                    for line in result["stdout"].strip().split("\n"):
                        try:
                            data = json.loads(line)
                            if data.get("type") == "warning":
                                results["vulnerabilities"].append(data)
                        except Exception:
                            pass
        
        if scanner in ("auto", "trivy"):
            # Container/filesystem scan
            cmd = f"trivy fs --format {format} --severity {severity.upper()} {resolved}"
            result = _run_command(cmd, cwd=str(resolved))
            if result["success"]:
                try:
                    data = json.loads(result["stdout"])
                    if isinstance(data, list):
                        for item in data:
                            if "Vulnerabilities" in item:
                                results["vulnerabilities"].extend(item["Vulnerabilities"])
                except Exception:
                    pass
        
        # Count by severity
        for vuln in results["vulnerabilities"]:
            sev = vuln.get("severity", "").lower()
            if sev in results["summary"]:
                results["summary"][sev] += 1
        
        results["total"] = len(results["vulnerabilities"])
        results["success"] = True
        
    except Exception as e:
        logger.exception("Vulnerability scan failed")
        results["success"] = False
        results["error"] = str(e)
    
    return json.dumps(results)


def detect_secrets(
    path: str = ".",
    patterns: Optional[List[str]] = None,
    exclude_patterns: Optional[List[str]] = None,
    max_file_size: int = 1024 * 1024,
    task_id: str = "default",
) -> str:
    """Detect secrets in codebase.
    
    Args:
        path: Path to scan
        patterns: Custom regex patterns (uses built-in if not provided)
        exclude_patterns: File patterns to exclude
        max_file_size: Maximum file size to scan
        task_id: Task identifier
        
    Returns:
        JSON with detected secrets
    """
    resolved = _resolve_path(path, task_id)
    file_ops = _get_file_ops(task_id)
    
    search_patterns = patterns or list(SECRET_PATTERNS.values())
    compiled_patterns = [(name, re.compile(pattern)) for name, pattern in SECRET_PATTERNS.items()]
    if patterns:
        for i, p in enumerate(patterns):
            compiled_patterns.append((f"custom_{i}", re.compile(p)))
    
    exclude = exclude_patterns or [
        "*.git/*", "node_modules/*", "*.pyc", "__pycache__/*",
        "*.lock", "*.log", "dist/*", "build/*", "*.min.js"
    ]
    
    results = {"secrets": [], "files_scanned": 0, "success": True}
    
    try:
        for file_path in resolved.rglob("*"):
            if not file_path.is_file():
                continue
            
            # Check exclude patterns
            rel_path = file_path.relative_to(resolved)
            if any(rel_path.match(pat) for pat in exclude):
                continue
            
            # Check file size
            try:
                if file_path.stat().st_size > max_file_size:
                    continue
            except Exception:
                continue
            
            # Skip binary files
            try:
                content = file_ops.read_text(file_path)
            except UnicodeDecodeError:
                continue
            except Exception:
                continue
            
            results["files_scanned"] += 1
            
            for line_num, line in enumerate(content.splitlines(), 1):
                for name, pattern in compiled_patterns:
                    matches = pattern.finditer(line)
                    for match in matches:
                        results["secrets"].append({
                            "file": str(rel_path),
                            "line": line_num,
                            "pattern": name,
                            "match": match.group()[:100],
                            "context": line.strip()[:200],
                        })
        
        results["total"] = len(results["secrets"])
        
    except Exception as e:
        logger.exception("Secret detection failed")
        results["success"] = False
        results["error"] = str(e)
    
    return json.dumps(results)


def static_analysis(
    path: str = ".",
    tools: Optional[List[str]] = None,
    config: Optional[str] = None,
    task_id: str = "default",
) -> str:
    """Run static analysis tools.
    
    Args:
        path: Path to analyze
        tools: Tools to run (bandit, semgrep, pylint, eslint, mypy, clippy, checkstyle)
        config: Config file path
        task_id: Task identifier
        
    Returns:
        JSON with static analysis results
    """
    resolved = _resolve_path(path, task_id)
    
    available_tools = {
        "bandit": {"cmd": "bandit -r {path} -f json", "lang": "python"},
        "semgrep": {"cmd": "semgrep --config=auto --json {path}", "lang": "all"},
        "pylint": {"cmd": "pylint --output-format=json {path}", "lang": "python"},
        "eslint": {"cmd": "eslint --format json {path}", "lang": "javascript"},
        "mypy": {"cmd": "mypy --json-report {path}", "lang": "python"},
        "clippy": {"cmd": "cargo clippy --message-format=json", "lang": "rust"},
        "checkstyle": {"cmd": "checkstyle -f json -c {config} {path}", "lang": "java"},
        "golangci-lint": {"cmd": "golangci-lint run --out-format=json {path}", "lang": "go"},
    }
    
    selected = tools or list(available_tools.keys())
    results = {"results": {}, "success": True}
    
    try:
        for tool in selected:
            if tool not in available_tools:
                results["results"][tool] = {"error": f"Unknown tool: {tool}"}
                continue
            
            tool_info = available_tools[tool]
            cmd = tool_info["cmd"].format(path=resolved, config=config or "")
            
            result = _run_command(cmd, cwd=str(resolved), timeout=600)
            
            if result["success"] or result["returncode"] in (1, 2):  # Some tools return non-zero on findings
                try:
                    if tool in ("bandit", "eslint", "golangci-lint"):
                        data = json.loads(result["stdout"])
                    elif tool == "semgrep":
                        data = json.loads(result["stdout"])
                    elif tool == "pylint":
                        data = json.loads(result["stdout"])
                    elif tool == "clippy":
                        data = [json.loads(line) for line in result["stdout"].strip().split("\n") if line]
                    else:
                        data = {"output": result["stdout"]}
                    results["results"][tool] = {"success": True, "data": data}
                except Exception:
                    results["results"][tool] = {"success": True, "raw": result["stdout"]}
            else:
                results["results"][tool] = {"success": False, "error": result["stderr"]}
        
    except Exception as e:
        logger.exception("Static analysis failed")
        results["success"] = False
        results["error"] = str(e)
    
    return json.dumps(results)


def detect_misconfig(
    path: str = ".",
    check_types: Optional[List[str]] = None,
    task_id: str = "default",
) -> str:
    """Detect misconfigurations.
    
    Args:
        path: Path to scan
        check_types: Types of checks (docker, kubernetes, terraform, cloudformation, github-actions, gitlab-ci)
        task_id: Task identifier
        
    Returns:
        JSON with misconfiguration findings
    """
    resolved = _resolve_path(path, task_id)
    
    checks = check_types or ["docker", "kubernetes", "terraform", "github-actions"]
    results = {"findings": [], "success": True}
    
    try:
        # Dockerfile checks
        if "docker" in checks:
            for dockerfile in resolved.rglob("Dockerfile*"):
                content = dockerfile.read_text()
                # Check for common issues
                if "USER root" in content and "USER " not in content.replace("USER root", ""):
                    results["findings"].append({
                        "type": "docker",
                        "file": str(dockerfile.relative_to(resolved)),
                        "issue": "Running as root user",
                        "severity": "high",
                    })
                if "--no-cache" not in content and "apt-get update" in content:
                    results["findings"].append({
                        "type": "docker",
                        "file": str(dockerfile.relative_to(resolved)),
                        "issue": "Missing --no-cache for apt-get update",
                        "severity": "medium",
                    })
        
        # Kubernetes checks
        if "kubernetes" in checks:
            for k8s_file in resolved.rglob("*.yaml"):
                if any(x in str(k8s_file) for x in ["k8s", "kubernetes", "deploy", "service", "ingress"]):
                    content = k8s_file.read_text()
                    if "privileged: true" in content:
                        results["findings"].append({
                            "type": "kubernetes",
                            "file": str(k8s_file.relative_to(resolved)),
                            "issue": "Privileged container",
                            "severity": "critical",
                        })
                    if "runAsUser: 0" in content or "runAsNonRoot: false" in content:
                        results["findings"].append({
                            "type": "kubernetes",
                            "file": str(k8s_file.relative_to(resolved)),
                            "issue": "Running as root",
                            "severity": "high",
                        })
        
        # Terraform checks
        if "terraform" in checks:
            for tf_file in resolved.rglob("*.tf"):
                content = tf_file.read_text()
                if "public" in content.lower() and "acl" in content.lower():
                    results["findings"].append({
                        "type": "terraform",
                        "file": str(tf_file.relative_to(resolved)),
                        "issue": "Potential public resource",
                        "severity": "medium",
                    })
        
        # GitHub Actions
        if "github-actions" in checks:
            for wf_file in resolved.rglob(".github/workflows/*.yml") + resolved.rglob(".github/workflows/*.yaml"):
                content = wf_file.read_text()
                if "actions/checkout@" in content and "actions/checkout@v" not in content:
                    results["findings"].append({
                        "type": "github-actions",
                        "file": str(wf_file.relative_to(resolved)),
                        "issue": "Unpinned GitHub Action",
                        "severity": "medium",
                    })
        
        results["total"] = len(results["findings"])
        
    except Exception as e:
        logger.exception("Misconfiguration detection failed")
        results["success"] = False
        results["error"] = str(e)
    
    return json.dumps(results)


def check_license(
    path: str = ".",
    allowed_licenses: Optional[List[str]] = None,
    denied_licenses: Optional[List[str]] = None,
    task_id: str = "default",
) -> str:
    """Check license compliance.
    
    Args:
        path: Path to scan
        allowed_licenses: List of allowed SPDX license IDs
        denied_licenses: List of denied SPDX license IDs
        task_id: Task identifier
        
    Returns:
        JSON with license compliance results
    """
    resolved = _resolve_path(path, task_id)
    
    allowed = set(allowed_licenses or ["MIT", "Apache-2.0", "BSD-3-Clause", "BSD-2-Clause", "ISC", "MPL-2.0"])
    denied = set(denied_licenses or ["GPL-3.0", "AGPL-3.0", "GPL-2.0", "LGPL-3.0"])
    
    results = {
        "packages": [],
        "violations": [],
        "summary": {"allowed": 0, "denied": 0, "unknown": 0},
        "success": True,
    }
    
    try:
        # Python
        if (resolved / "requirements.txt").exists() or (resolved / "pyproject.toml").exists():
            result = _run_command("pip-licenses --format=json", cwd=str(resolved))
            if result["success"]:
                try:
                    data = json.loads(result["stdout"])
                    for pkg in data:
                        license_name = pkg.get("License", "Unknown")
                        results["packages"].append({
                            "name": pkg.get("Name"),
                            "version": pkg.get("Version"),
                            "license": license_name,
                            "language": "python",
                        })
                        if license_name in denied:
                            results["violations"].append({
                                "package": pkg.get("Name"),
                                "license": license_name,
                                "reason": "Denied license",
                            })
                            results["summary"]["denied"] += 1
                        elif license_name in allowed:
                            results["summary"]["allowed"] += 1
                        else:
                            results["summary"]["unknown"] += 1
                except Exception:
                    pass
        
        # Node.js
        if (resolved / "package.json").exists():
            result = _run_command("license-checker --json", cwd=str(resolved))
            if result["success"]:
                try:
                    data = json.loads(result["stdout"])
                    for name, info in data.items():
                        license_name = info.get("licenses", "Unknown")
                        results["packages"].append({
                            "name": name,
                            "version": info.get("version"),
                            "license": license_name,
                            "language": "javascript",
                        })
                        if license_name in denied:
                            results["violations"].append({
                                "package": name,
                                "license": license_name,
                                "reason": "Denied license",
                            })
                            results["summary"]["denied"] += 1
                        elif license_name in allowed:
                            results["summary"]["allowed"] += 1
                        else:
                            results["summary"]["unknown"] += 1
                except Exception:
                    pass
        
        # Cargo
        if (resolved / "Cargo.toml").exists():
            result = _run_command("cargo license --json", cwd=str(resolved))
            if result["success"]:
                try:
                    data = json.loads(result["stdout"])
                    for pkg in data:
                        license_name = pkg.get("license", "Unknown")
                        results["packages"].append({
                            "name": pkg.get("name"),
                            "version": pkg.get("version"),
                            "license": license_name,
                            "language": "rust",
                        })
                        if license_name in denied:
                            results["violations"].append({
                                "package": pkg.get("name"),
                                "license": license_name,
                                "reason": "Denied license",
                            })
                            results["summary"]["denied"] += 1
                        elif license_name in allowed:
                            results["summary"]["allowed"] += 1
                        else:
                            results["summary"]["unknown"] += 1
                except Exception:
                    pass
        
        results["compliant"] = results["summary"]["denied"] == 0
        
    except Exception as e:
        logger.exception("License check failed")
        results["success"] = False
        results["error"] = str(e)
    
    return json.dumps(results)


def generate_sbom(
    path: str = ".",
    format: str = "spdx",
    output: Optional[str] = None,
    task_id: str = "default",
) -> str:
    """Generate Software Bill of Materials (SBOM).
    
    Args:
        path: Path to scan
        format: Output format (spdx, cyclonedx, json)
        output: Output file path
        task_id: Task identifier
        
    Returns:
        JSON with SBOM or file path
    """
    resolved = _resolve_path(path, task_id)
    
    results = {"sbom": None, "path": None, "success": True}
    
    try:
        # Try syft first (supports multiple formats)
        cmd = f"syft {resolved} -o {format}"
        if output:
            cmd += f" --file {output}"
        
        result = _run_command(cmd, cwd=str(resolved))
        
        if result["success"]:
            if output:
                results["path"] = output
                results["message"] = f"SBOM written to {output}"
            else:
                results["sbom"] = result["stdout"]
        else:
            # Fallback to cyclonedx-bom for Java/Maven
            if (resolved / "pom.xml").exists():
                cmd = f"cyclonedx-bom -o {output or 'bom.xml'}"
                result = _run_command(cmd, cwd=str(resolved))
                if result["success"]:
                    results["path"] = output or "bom.xml"
                    results["message"] = f"CycloneDX SBOM generated"
            else:
                results["success"] = False
                results["error"] = "No SBOM generator available. Install syft or cyclonedx-bom"
        
    except Exception as e:
        logger.exception("SBOM generation failed")
        results["success"] = False
        results["error"] = str(e)
    
    return json.dumps(results)


def generate_security_report(
    path: str = ".",
    include_vulns: bool = True,
    include_secrets: bool = True,
    include_misconfig: bool = True,
    include_licenses: bool = True,
    format: str = "json",
    output: Optional[str] = None,
    task_id: str = "default",
) -> str:
    """Generate comprehensive security report.
    
    Args:
        path: Path to analyze
        include_vulns: Include vulnerability scan
        include_secrets: Include secret detection
        include_misconfig: Include misconfiguration detection
        include_licenses: Include license check
        format: Report format (json, html, markdown)
        output: Output file path
        task_id: Task identifier
        
    Returns:
        JSON with report
    """
    resolved = _resolve_path(path, task_id)
    
    report = {
        "path": str(resolved),
        "timestamp": __import__("time").time(),
        "sections": {},
        "summary": {},
    }
    
    try:
        if include_vulns:
            vuln_result = json.loads(scan_vulnerabilities(str(resolved), task_id=task_id))
            report["sections"]["vulnerabilities"] = vuln_result
        
        if include_secrets:
            secret_result = json.loads(detect_secrets(str(resolved), task_id=task_id))
            report["sections"]["secrets"] = secret_result
        
        if include_misconfig:
            misconfig_result = json.loads(detect_misconfig(str(resolved), task_id=task_id))
            report["sections"]["misconfigurations"] = misconfig_result
        
        if include_licenses:
            license_result = json.loads(check_license(str(resolved), task_id=task_id))
            report["sections"]["licenses"] = license_result
        
        # Generate summary
        report["summary"]["vulnerabilities"] = report["sections"].get("vulnerabilities", {}).get("total", 0)
        report["summary"]["secrets"] = report["sections"].get("secrets", {}).get("total", 0)
        report["summary"]["misconfigurations"] = report["sections"].get("misconfigurations", {}).get("total", 0)
        report["summary"]["license_violations"] = len(report["sections"].get("licenses", {}).get("violations", []))
        report["summary"]["compliant"] = (
            report["summary"]["vulnerabilities"] == 0 and
            report["summary"]["secrets"] == 0 and
            report["summary"]["misconfigurations"] == 0 and
            report["summary"]["license_violations"] == 0
        )
        
        # Format output
        if format == "markdown":
            md = f"# Security Report for {resolved.name}\n\n"
            md += f"**Timestamp:** {__import__('datetime').datetime.fromtimestamp(report['timestamp']).isoformat()}\n\n"
            md += f"**Compliant:** {report['summary']['compliant']}\n\n"
            md += "## Summary\n\n"
            for key, value in report["summary"].items():
                md += f"- {key}: {value}\n"
            md += "\n"
            report["formatted"] = md
        
        elif format == "html":
            html = f"<html><head><title>Security Report</title></head><body>"
            html += f"<h1>Security Report for {resolved.name}</h1>"
            html += f"<p>Compliant: {report['summary']['compliant']}</p>"
            html += "<h2>Summary</h2><ul>"
            for key, value in report["summary"].items():
                html += f"<li>{key}: {value}</li>"
            html += "</ul></body></html>"
            report["formatted"] = html
        
        if output:
            out_path = Path(output)
            if format in ("markdown", "html"):
                out_path.write_text(report.get("formatted", ""))
            else:
                out_path.write_text(json.dumps(report, indent=2))
            report["output_path"] = str(out_path)
        
        report["success"] = True
        
    except Exception as e:
        logger.exception("Security report generation failed")
        report["success"] = False
        report["error"] = str(e)
    
    return json.dumps(report)


def _register_security_tools():
    """Register all security tools with the registry."""
    tools = [
        ("scan_vulnerabilities", scan_vulnerabilities, "Scan for vulnerabilities in dependencies"),
        ("detect_secrets", detect_secrets, "Detect secrets in codebase"),
        ("static_analysis", static_analysis, "Run static analysis tools (bandit, semgrep, etc.)"),
        ("detect_misconfig", detect_misconfig, "Detect misconfigurations"),
        ("check_license", check_license, "Check license compliance"),
        ("generate_sbom", generate_sbom, "Generate Software Bill of Materials (SPDX, CycloneDX)"),
        ("generate_security_report", generate_security_report, "Generate comprehensive security report"),
    ]
    
    for name, func, desc in tools:
        registry.register(
            name=name,
            toolset="security",
            schema={"name": name, "description": desc, "parameters": {"type": "object", "properties": {}}},
            handler=func,
            check_fn=lambda: True,
            description=desc,
        )


_register_security_tools()