#!/usr/bin/env python3
"""
Git Tools Module

Extends Hermes with comprehensive Git operations:
- Repository cloning with auth options
- Repository analysis (stats, contributors, history)
- Commit generation with conventional messages
- Branch management (create, list, delete, switch)
- Merge with conflict detection
- Conflict explanation
- Diff summarization
- Automated code review
- Release tagging
- Repository statistics
- Pull request preparation
- Automatic changelog generation

All operations use the existing terminal tool infrastructure and
respect workspace boundaries.
"""

import json
import logging
import os
import re
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from tools.registry import registry
from tools.file_tools import _resolve_path_for_task, _get_file_ops
from tools.terminal_tool import terminal_tool

logger = logging.getLogger(__name__)


def _run_git_command(
    command: str,
    repo_path: str,
    task_id: str = "default",
    timeout: int = 60,
) -> Dict[str, Any]:
    """Run a git command in the repository."""
    try:
        # Use terminal tool to execute git command
        result = terminal_tool(
            command=f"cd {repo_path} && {command}",
            task_id=task_id,
            timeout=timeout,
        )
        return json.loads(result)
    except Exception as e:
        logger.exception("Git command failed: %s", e)
        return {"error": f"Git command failed: {e}", "success": False}


def _resolve_repo_path(path: str, task_id: str = "default") -> Path:
    """Resolve repository path."""
    return _resolve_path_for_task(path, task_id)


def git_clone(
    url: str,
    destination: Optional[str] = None,
    branch: Optional[str] = None,
    depth: Optional[int] = None,
    recursive: bool = False,
    auth_token: Optional[str] = None,
    task_id: str = "default",
) -> str:
    """Clone a Git repository."""
    try:
        file_ops = _get_file_ops(task_id)
        
        # Build clone command
        cmd_parts = ["git", "clone"]
        
        if depth:
            cmd_parts.extend(["--depth", str(depth)])
        if recursive:
            cmd_parts.append("--recursive")
        if branch:
            cmd_parts.extend(["--branch", branch])
        
        # Handle authentication
        clone_url = url
        if auth_token and "github.com" in url:
            clone_url = url.replace("https://", f"https://{auth_token}@")
        
        cmd_parts.append(clone_url)
        
        if destination:
            dest_path = _resolve_path_for_task(destination, task_id)
            cmd_parts.append(str(dest_path))
        else:
            # Auto-detect destination from URL
            repo_name = url.rstrip('/').split('/')[-1].replace('.git', '')
            dest_path = _resolve_path_for_task(repo_name, task_id)
            cmd_parts.append(str(dest_path))
        
        # Ensure parent directory exists
        if not file_ops.exists(dest_path.parent):
            file_ops.makedirs(dest_path.parent, exist_ok=True)
        
        command = " ".join(cmd_parts)
        result = _run_git_command(command, str(dest_path.parent), task_id)
        
        if result.get("success"):
            return json.dumps({
                "success": True,
                "repository": str(dest_path),
                "url": url,
                "branch": branch,
            })
        else:
            return json.dumps({
                "success": False,
                "error": result.get("error", "Clone failed"),
            })
    
    except Exception as e:
        logger.exception("git_clone error: %s", e)
        return json.dumps({"error": f"Clone failed: {e}"})


def git_analyze(
    repo_path: str = ".",
    include_stats: bool = True,
    include_contributors: bool = True,
    include_history: bool = True,
    max_commits: int = 100,
    task_id: str = "default",
) -> str:
    """Analyze a Git repository."""
    try:
        resolved = _resolve_repo_path(repo_path, task_id)
        file_ops = _get_file_ops(task_id)
        
        if not file_ops.exists(resolved / ".git"):
            return json.dumps({"error": f"Not a Git repository: {repo_path}"})
        
        analysis = {"repository": str(resolved)}
        
        if include_stats:
            # Basic stats
            stats_result = _run_git_command(
                "git rev-list --count HEAD && git ls-files | wc -l && git ls-files | xargs wc -l",
                str(resolved), task_id
            )
            if stats_result.get("success"):
                output = result.get("stdout", "").strip().split('\n')
                if len(output) >= 3:
                    analysis["total_commits"] = int(output[0].strip()) if output[0].strip().isdigit() else 0
                    analysis["total_files"] = int(output[1].strip()) if output[1].strip().isdigit() else 0
                    analysis["total_lines"] = int(output[2].strip().split()[0]) if output[2].strip() else 0
            
            # Repo size
            size_result = _run_git_command(
                "du -sh .git",
                str(resolved), task_id
            )
            if size_result.get("success"):
                analysis["git_size"] = size_result.get("stdout", "").split()[0]
        
        if include_contributors:
            # Contributors
            contrib_result = _run_git_command(
                "git shortlog -sn --all | head -20",
                str(resolved), task_id
            )
            if contrib_result.get("success"):
                contributors = []
                for line in contrib_result.get("stdout", "").strip().split('\n'):
                    if line.strip():
                        parts = line.strip().split('\t', 1)
                        if len(parts) == 2:
                            contributors.append({
                                "commits": int(parts[0]),
                                "name": parts[1],
                            })
                analysis["contributors"] = contributors
        
        if include_history:
            # Recent commits
            log_result = _run_git_command(
                f"git log --oneline -n {max_commits} --pretty=format:'%h|%an|%ad|%s' --date=short",
                str(resolved), task_id
            )
            if log_result.get("success"):
                commits = []
                for line in log_result.get("stdout", "").strip().split('\n'):
                    if line.strip():
                        parts = line.split('|', 3)
                        if len(parts) == 4:
                            commits.append({
                                "hash": parts[0],
                                "author": parts[1],
                                "date": parts[2],
                                "message": parts[3],
                            })
                analysis["recent_commits"] = commits
        
        # Branches
        branch_result = _run_git_command(
            "git branch -a --format='%(refname:short)|%(upstream:short)|%(HEAD)'",
            str(resolved), task_id
        )
        if branch_result.get("success"):
            branches = []
            for line in branch_result.get("stdout", "").strip().split('\n'):
                if line.strip():
                    parts = line.split('|')
                    branches.append({
                        "name": parts[0],
                        "upstream": parts[1] if len(parts) > 1 else None,
                        "is_current": parts[2] == '*' if len(parts) > 2 else False,
                    })
            analysis["branches"] = branches
        
        # Remotes
        remote_result = _run_git_command(
            "git remote -v",
            str(resolved), task_id
        )
        if remote_result.get("success"):
            remotes = []
            for line in remote_result.get("stdout", "").strip().split('\n'):
                if line.strip():
                    parts = line.split()
                    if len(parts) >= 2:
                        remotes.append({
                            "name": parts[0],
                            "url": parts[1],
                            "type": parts[2].strip('()') if len(parts) > 2 else "fetch",
                        })
            analysis["remotes"] = remotes
        
        return json.dumps(analysis, indent=2)
    
    except Exception as e:
        logger.exception("git_analyze error: %s", e)
        return json.dumps({"error": f"Analysis failed: {e}"})


def git_commit(
    repo_path: str = ".",
    message: str = "",
    files: Optional[List[str]] = None,
    all_changes: bool = False,
    sign: bool = False,
    conventional: bool = True,
    task_id: str = "default",
) -> str:
    """Create a Git commit with optional conventional message formatting."""
    try:
        resolved = _resolve_repo_path(repo_path, task_id)
        file_ops = _get_file_ops(task_id)
        
        if not file_ops.exists(resolved / ".git"):
            return json.dumps({"error": f"Not a Git repository: {repo_path}"})
        
        # Stage files
        if files:
            for f in files:
                file_path = resolved / f
                if file_ops.exists(file_path):
                    result = _run_git_command(f"git add {f}", str(resolved), task_id)
                    if not result.get("success"):
                        return json.dumps({"error": f"Failed to stage {f}: {result.get('error')}"})
        elif all_changes:
            result = _run_git_command("git add -A", str(resolved), task_id)
            if not result.get("success"):
                return json.dumps({"error": f"Failed to stage changes: {result.get('error')}"})
        else:
            return json.dumps({"error": "No files specified. Use files list or all_changes=true"})
        
        # Generate conventional commit message if requested
        if conventional and not message:
            # Try to generate from staged changes
            diff_result = _run_git_command(
                "git diff --cached --stat",
                str(resolved), task_id
            )
            if diff_result.get("success"):
                stats = diff_result.get("stdout", "").strip()
                if stats:
                    # Simple heuristic for commit type
                    if "test" in stats.lower():
                        prefix = "test"
                    elif "doc" in stats.lower() or "readme" in stats.lower():
                        prefix = "docs"
                    elif "fix" in stats.lower() or "bug" in stats.lower():
                        prefix = "fix"
                    elif "feat" in stats.lower() or "add" in stats.lower():
                        prefix = "feat"
                    elif "refactor" in stats.lower():
                        prefix = "refactor"
                    elif "style" in stats.lower() or "format" in stats.lower():
                        prefix = "style"
                    elif "chore" in stats.lower() or "build" in stats.lower() or "ci" in stats.lower():
                        prefix = "chore"
                    else:
                        prefix = "chore"
                    
                    message = f"{prefix}: update files ({stats.split()[0]} files changed)"
        
        if not message:
            return json.dumps({"error": "Commit message required"})
        
        # Commit
        commit_cmd = "git commit"
        if sign:
            commit_cmd += " -S"
        commit_cmd += f' -m "{message}"'
        
        result = _run_git_command(commit_cmd, str(resolved), task_id)
        
        if result.get("success"):
            # Get commit hash
            hash_result = _run_git_command(
                "git rev-parse HEAD",
                str(resolved), task_id
            )
            commit_hash = hash_result.get("stdout", "").strip() if hash_result.get("success") else "unknown"
            
            return json.dumps({
                "success": True,
                "commit_hash": commit_hash,
                "message": message,
                "repository": str(resolved),
            })
        else:
            return json.dumps({
                "success": False,
                "error": result.get("error", "Commit failed"),
            })
    
    except Exception as e:
        logger.exception("git_commit error: %s", e)
        return json.dumps({"error": f"Commit failed: {e}"})


def git_branch(
    repo_path: str = ".",
    action: str = "list",  # list, create, delete, switch, rename
    branch_name: Optional[str] = None,
    new_name: Optional[str] = None,
    start_point: Optional[str] = None,
    force: bool = False,
    task_id: str = "default",
) -> str:
    """Manage Git branches."""
    try:
        resolved = _resolve_repo_path(repo_path, task_id)
        file_ops = _get_file_ops(task_id)
        
        if not file_ops.exists(resolved / ".git"):
            return json.dumps({"error": f"Not a Git repository: {repo_path}"})
        
        if action == "list":
            result = _run_git_command(
                "git branch -a --format='%(refname:short)|%(upstream:short)|%(HEAD)|%(objectname:short)'",
                str(resolved), task_id
            )
            if result.get("success"):
                branches = []
                for line in result.get("stdout", "").strip().split('\n'):
                    if line.strip():
                        parts = line.split('|')
                        branches.append({
                            "name": parts[0],
                            "upstream": parts[1] if len(parts) > 1 and parts[1] else None,
                            "is_current": parts[2] == '*' if len(parts) > 2 else False,
                            "commit": parts[3] if len(parts) > 3 else None,
                        })
                return json.dumps({"branches": branches})
            else:
                return json.dumps({"error": result.get("error", "Failed to list branches")})
        
        elif action == "create":
            if not branch_name:
                return json.dumps({"error": "Branch name required for create"})
            
            cmd = f"git branch {branch_name}"
            if start_point:
                cmd += f" {start_point}"
            
            result = _run_git_command(cmd, str(resolved), task_id)
            if result.get("success"):
                return json.dumps({"success": True, "branch": branch_name})
            else:
                return json.dumps({"error": result.get("error", "Failed to create branch")})
        
        elif action == "delete":
            if not branch_name:
                return json.dumps({"error": "Branch name required for delete"})
            
            flag = "-D" if force else "-d"
            result = _run_git_command(f"git branch {flag} {branch_name}", str(resolved), task_id)
            if result.get("success"):
                return json.dumps({"success": True, "branch": branch_name})
            else:
                return json.dumps({"error": result.get("error", "Failed to delete branch")})
        
        elif action == "switch":
            if not branch_name:
                return json.dumps({"error": "Branch name required for switch"})
            
            result = _run_git_command(f"git checkout {branch_name}", str(resolved), task_id)
            if result.get("success"):
                return json.dumps({"success": True, "branch": branch_name})
            else:
                return json.dumps({"error": result.get("error", "Failed to switch branch")})
        
        elif action == "rename":
            if not branch_name or not new_name:
                return json.dumps({"error": "Both branch_name and new_name required for rename"})
            
            result = _run_git_command(f"git branch -m {branch_name} {new_name}", str(resolved), task_id)
            if result.get("success"):
                return json.dumps({"success": True, "old_name": branch_name, "new_name": new_name})
            else:
                return json.dumps({"error": result.get("error", "Failed to rename branch")})
        
        else:
            return json.dumps({"error": f"Invalid action: {action}"})
    
    except Exception as e:
        logger.exception("git_branch error: %s", e)
        return json.dumps({"error": f"Branch operation failed: {e}"})


def git_merge(
    repo_path: str = ".",
    source_branch: str = "",
    target_branch: Optional[str] = None,
    no_ff: bool = False,
    squash: bool = False,
    strategy: Optional[str] = None,
    task_id: str = "default",
) -> str:
    """Merge branches with conflict detection."""
    try:
        resolved = _resolve_repo_path(repo_path, task_id)
        file_ops = _get_file_ops(task_id)
        
        if not file_ops.exists(resolved / ".git"):
            return json.dumps({"error": f"Not a Git repository: {repo_path}"})
        
        if not source_branch:
            return json.dumps({"error": "Source branch required"})
        
        # Switch to target branch if specified
        if target_branch:
            checkout_result = _run_git_command(f"git checkout {target_branch}", str(resolved), task_id)
            if not checkout_result.get("success"):
                return json.dumps({"error": f"Failed to checkout {target_branch}: {checkout_result.get('error')}"})
        
        # Build merge command
        cmd = "git merge"
        if no_ff:
            cmd += " --no-ff"
        if squash:
            cmd += " --squash"
        if strategy:
            cmd += f" -s {strategy}"
        cmd += f" {source_branch}"
        
        result = _run_git_command(cmd, str(resolved), task_id)
        
        if result.get("success"):
            return json.dumps({
                "success": True,
                "merged": True,
                "source": source_branch,
                "target": target_branch or "current",
            })
        else:
            # Check for conflicts
            error = result.get("error", "")
            if "conflict" in error.lower() or "CONFLICT" in error:
                # Get conflicted files
                status_result = _run_git_command("git status --porcelay", str(resolved), task_id)
                conflicts = []
                if status_result.get("success"):
                    for line in status_result.get("stdout", "").strip().split('\n'):
                        if line.startswith("UU") or line.startswith("AA") or line.startswith("DD"):
                            conflicts.append(line[3:].strip())
                
                return json.dumps({
                    "success": False,
                    "merged": False,
                    "conflicts": True,
                    "conflicted_files": conflicts,
                    "error": "Merge conflicts detected",
                })
            else:
                return json.dumps({
                    "success": False,
                    "merged": False,
                    "error": error,
                })
    
    except Exception as e:
        logger.exception("git_merge error: %s", e)
        return json.dumps({"error": f"Merge failed: {e}"})


def git_conflict_explain(
    repo_path: str = ".",
    file_path: Optional[str] = None,
    task_id: str = "default",
) -> str:
    """Explain merge conflicts in a repository or specific file."""
    try:
        resolved = _resolve_repo_path(repo_path, task_id)
        file_ops = _get_file_ops(task_id)
        
        if not file_ops.exists(resolved / ".git"):
            return json.dumps({"error": f"Not a Git repository: {repo_path}"})
        
        # Get conflicted files
        status_result = _run_git_command("git status --porcelain", str(resolved), task_id)
        conflicts = []
        
        if status_result.get("success"):
            for line in status_result.get("stdout", "").strip().split('\n'):
                if line.startswith("UU") or line.startswith("AA") or line.startswith("DD"):
                    fname = line[3:].strip()
                    if file_path is None or fname == file_path:
                        # Read the conflicted file
                        full_path = resolved / fname
                        if file_ops.exists(full_path):
                            content = file_ops.read(full_path)
                            conflicts.append({
                                "file": fname,
                                "content": content,
                            })
        
        if not conflicts:
            return json.dumps({"message": "No conflicts found"})
        
        if file_path and len(conflicts) == 1:
            # Provide detailed explanation for single file
            conflict = conflicts[0]
            explanation = _explain_conflict(conflict["content"])
            return json.dumps({
                "file": conflict["file"],
                "conflicts": explanation,
            })
        
        return json.dumps({
            "conflicted_files": [c["file"] for c in conflicts],
            "count": len(conflicts),
        })
    
    except Exception as e:
        logger.exception("git_conflict_explain error: %s", e)
        return json.dumps({"error": f"Conflict explanation failed: {e}"})


def _explain_conflict(content: str) -> List[Dict]:
    """Parse and explain conflict markers in content."""
    conflicts = []
    lines = content.split('\n')
    i = 0
    while i < len(lines):
        if lines[i].startswith('<<<<<<< '):
            # Found conflict start
            ours_start = i
            theirs_start = None
            end = None
            
            for j in range(i + 1, len(lines)):
                if lines[j].startswith('=======') and theirs_start is None:
                    theirs_start = j
                elif lines[j].startswith('>>>>>>> '):
                    end = j
                    break
            
            if theirs_start is not None and end is not None:
                ours_content = '\n'.join(lines[ours_start + 1:theirs_start])
                theirs_content = '\n'.join(lines[theirs_start + 1:end])
                marker = lines[end][8:].strip()  # Remove '>>>>>>> '
                
                conflicts.append({
                    "type": "merge_conflict",
                    "ours": ours_content,
                    "theirs": theirs_content,
                    "source": marker,
                    "line_start": ours_start + 1,
                    "line_end": end + 1,
                })
                i = end + 1
            else:
                i += 1
        else:
            i += 1
    
    return conflicts


def git_diff(
    repo_path: str = ".",
    source: Optional[str] = None,
    target: Optional[str] = None,
    files: Optional[List[str]] = None,
    summary: bool = True,
    task_id: str = "default",
) -> str:
    """Show and summarize Git diffs."""
    try:
        resolved = _resolve_repo_path(repo_path, task_id)
        file_ops = _get_file_ops(task_id)
        
        if not file_ops.exists(resolved / ".git"):
            return json.dumps({"error": f"Not a Git repository: {repo_path}"})
        
        cmd = "git diff"
        if summary:
            cmd += " --stat"
        if source:
            cmd += f" {source}"
        if target:
            cmd += f" {target}"
        if files:
            cmd += " -- " + " ".join(files)
        
        result = _run_git_command(cmd, str(resolved), task_id)
        
        if result.get("success"):
            output = result.get("stdout", "")
            if summary:
                # Parse stat output
                files_changed = 0
                insertions = 0
                deletions = 0
                
                for line in output.strip().split('\n'):
                    if "file changed" in line or "files changed" in line:
                        parts = line.split(',')
                        for part in parts:
                            part = part.strip()
                            if "file changed" in part:
                                files_changed = int(part.split()[0])
                            elif "insertion" in part:
                                insertions = int(part.split()[0])
                            elif "deletion" in part:
                                deletions = int(part.split()[0])
                
                return json.dumps({
                    "summary": {
                        "files_changed": files_changed,
                        "insertions": insertions,
                        "deletions": deletions,
                    },
                    "diff": output,
                })
            else:
                return json.dumps({"diff": output})
        else:
            return json.dumps({"error": result.get("error", "Diff failed")})
    
    except Exception as e:
        logger.exception("git_diff error: %s", e)
        return json.dumps({"error": f"Diff failed: {e}"})


def git_code_review(
    repo_path: str = ".",
    source_branch: str = "",
    target_branch: str = "main",
    focus_areas: Optional[List[str]] = None,
    task_id: str = "default",
) -> str:
    """Perform automated code review on a branch."""
    try:
        resolved = _resolve_repo_path(repo_path, task_id)
        file_ops = _get_file_ops(task_id)
        
        if not file_ops.exists(resolved / ".git"):
            return json.dumps({"error": f"Not a Git repository: {repo_path}"})
        
        if not source_branch:
            return json.dumps({"error": "Source branch required"})
        
        # Get diff between branches
        diff_result = _run_git_command(
            f"git diff {target_branch}...{source_branch} --no-color",
            str(resolved), task_id
        )
        
        if not diff_result.get("success"):
            return json.dumps({"error": f"Failed to get diff: {diff_result.get('error')}"})
        
        diff = diff_result.get("stdout", "")
        
        # Analyze diff for common issues
        issues = []
        
        # Check for TODO/FIXME comments
        todo_pattern = re.compile(r'(TODO|FIXME|XXX|HACK):\s*(.+)')
        for match in todo_pattern.finditer(diff):
            issues.append({
                "type": "todo",
                "severity": "info",
                "message": match.group(2).strip(),
            })
        
        # Check for large files added
        large_file_pattern = re.compile(r'new file mode.*\n.*?(\d+)\s+bytes')
        for match in large_file_pattern.finditer(diff):
            size = int(match.group(1))
            if size > 100000:  # 100KB
                issues.append({
                    "type": "large_file",
                    "severity": "warning",
                    "message": f"Large file added: {size} bytes",
                })
        
        # Check for debug prints
        debug_pattern = re.compile(r'(console\.log|print\(|debugger|console\.debug)')
        for match in debug_pattern.finditer(diff):
            issues.append({
                "type": "debug_code",
                "severity": "warning",
                "message": "Debug code detected",
            })
        
        # Check for potential secrets (basic patterns)
        secret_patterns = [
            (r'(api[_-]?key|secret|password|token)\s*[:=]\s*["\']?[a-zA-Z0-9_-]{20,}', "potential_secret"),
            (r'(aws_access_key_id|aws_secret_access_key)\s*[:=]\s*["\']?[A-Z0-9]{20,}', "aws_credentials"),
        ]
        
        for pattern, issue_type in secret_patterns:
            for match in re.finditer(pattern, diff, re.IGNORECASE):
                issues.append({
                    "type": issue_type,
                    "severity": "critical",
                    "message": "Potential secret detected in diff",
                })
        
        # Get changed files summary
        stat_result = _run_git_command(
            f"git diff {target_branch}...{source_branch} --stat",
            str(resolved), task_id
        )
        
        return json.dumps({
            "source_branch": source_branch,
            "target_branch": target_branch,
            "issues": issues,
            "issue_count": len(issues),
            "stat": stat_result.get("stdout", "") if stat_result.get("success") else "",
        })
    
    except Exception as e:
        logger.exception("git_code_review error: %s", e)
        return json.dumps({"error": f"Code review failed: {e}"})


def git_release(
    repo_path: str = ".",
    version: str = "",
    tag_name: Optional[str] = None,
    message: Optional[str] = None,
    push: bool = False,
    task_id: str = "default",
) -> str:
    """Create a release tag."""
    try:
        resolved = _resolve_repo_path(repo_path, task_id)
        file_ops = _get_file_ops(task_id)
        
        if not file_ops.exists(resolved / ".git"):
            return json.dumps({"error": f"Not a Git repository: {repo_path}"})
        
        if not version:
            return json.dumps({"error": "Version required"})
        
        tag = tag_name or f"v{version}"
        msg = message or f"Release {version}"
        
        # Create annotated tag
        result = _run_git_command(
            f'git tag -a {tag} -m "{msg}"',
            str(resolved), task_id
        )
        
        if result.get("success"):
            if push:
                push_result = _run_git_command(
                    f"git push origin {tag}",
                    str(resolved), task_id
                )
                if not push_result.get("success"):
                    return json.dumps({
                        "success": True,
                        "tag": tag,
                        "pushed": False,
                        "push_error": push_result.get("error"),
                    })
            
            return json.dumps({
                "success": True,
                "tag": tag,
                "version": version,
                "message": msg,
                "pushed": push,
            })
        else:
            return json.dumps({"error": result.get("error", "Tag creation failed")})
    
    except Exception as e:
        logger.exception("git_release error: %s", e)
        return json.dumps({"error": f"Release failed: {e}"})


def git_stats(
    repo_path: str = ".",
    since: Optional[str] = None,
    until: Optional[str] = None,
    author: Optional[str] = None,
    task_id: str = "default",
) -> str:
    """Get repository statistics."""
    try:
        resolved = _resolve_repo_path(repo_path, task_id)
        file_ops = _get_file_ops(task_id)
        
        if not file_ops.exists(resolved / ".git"):
            return json.dumps({"error": f"Not a Git repository: {repo_path}"})
        
        stats = {}
        
        # Commit count
        cmd = "git rev-list --count HEAD"
        if since:
            cmd += f" --since='{since}'"
        if until:
            cmd += f" --until='{until}'"
        if author:
            cmd += f" --author='{author}'"
        
        result = _run_git_command(cmd, str(resolved), task_id)
        if result.get("success"):
            stats["commits"] = int(result.get("stdout", "0").strip())
        
        # Contributors
        contrib_cmd = "git shortlog -sn"
        if since:
            contrib_cmd += f" --since='{since}'"
        if until:
            contrib_cmd += f" --until='{until}'"
        
        result = _run_git_command(contrib_cmd, str(resolved), task_id)
        if result.get("success"):
            contributors = []
            for line in result.get("stdout", "").strip().split('\n'):
                if line.strip():
                    parts = line.strip().split('\t', 1)
                    if len(parts) == 2:
                        contributors.append({
                            "commits": int(parts[0]),
                            "name": parts[1],
                        })
            stats["contributors"] = contributors
            stats["total_contributors"] = len(contributors)
        
        # Files changed
        files_cmd = "git diff --stat HEAD~10..HEAD"
        result = _run_git_command(files_cmd, str(resolved), task_id)
        if result.get("success"):
            stats["recent_changes"] = result.get("stdout", "")
        
        # Lines of code by language
        loc_cmd = "git ls-files | xargs file --mime-type | grep -v binary | cut -d: -f2 | sort | uniq -c | sort -rn"
        result = _run_git_command(loc_cmd, str(resolved), task_id)
        if result.get("success"):
            stats["file_types"] = result.get("stdout", "")
        
        return json.dumps(stats)
    
    except Exception as e:
        logger.exception("git_stats error: %s", e)
        return json.dumps({"error": f"Stats failed: {e}"})


def git_pr_prepare(
    repo_path: str = ".",
    source_branch: str = "",
    target_branch: str = "main",
    title: Optional[str] = None,
    body: Optional[str] = None,
    draft: bool = False,
    task_id: str = "default",
) -> str:
    """Prepare a pull request with generated description."""
    try:
        resolved = _resolve_repo_path(repo_path, task_id)
        file_ops = _get_file_ops(task_id)
        
        if not file_ops.exists(resolved / ".git"):
            return json.dumps({"error": f"Not a Git repository: {repo_path}"})
        
        if not source_branch:
            return json.dumps({"error": "Source branch required"})
        
        # Get commits for PR description
        log_result = _run_git_command(
            f"git log {target_branch}..{source_branch} --pretty=format:'- %s (%h)' --reverse",
            str(resolved), task_id
        )
        
        commits = []
        if log_result.get("success"):
            for line in log_result.get("stdout", "").strip().split('\n'):
                if line.strip():
                    commits.append(line.strip())
        
        # Get diff stat
        stat_result = _run_git_command(
            f"git diff {target_branch}...{source_branch} --stat",
            str(resolved), task_id
        )
        
        # Generate PR title if not provided
        if not title:
            # Use first commit message or branch name
            if commits:
                title = commits[0].replace('- ', '').split(' (')[0]
            else:
                title = f"Merge {source_branch} into {target_branch}"
        
        # Generate PR body if not provided
        if not body:
            body_parts = []
            if commits:
                body_parts.append("## Changes\n")
                body_parts.extend(commits[:20])  # Limit to 20 commits
                if len(commits) > 20:
                    body_parts.append(f"\n... and {len(commits) - 20} more commits")
            
            if stat_result.get("success"):
                body_parts.append("\n## Diffstat\n")
                body_parts.append("```")
                body_parts.append(stat_result.get("stdout", ""))
                body_parts.append("```")
            
            body = "\n".join(body_parts)
        
        return json.dumps({
            "title": title,
            "body": body,
            "source_branch": source_branch,
            "target_branch": target_branch,
            "draft": draft,
            "commits": commits,
            "commit_count": len(commits),
        })
    
    except Exception as e:
        logger.exception("git_pr_prepare error: %s", e)
        return json.dumps({"error": f"PR preparation failed: {e}"})


def git_changelog(
    repo_path: str = ".",
    from_tag: Optional[str] = None,
    to_tag: Optional[str] = None,
    format: str = "markdown",  # markdown, json, text
    group_by_type: bool = True,
    task_id: str = "default",
) -> str:
    """Generate changelog from Git history."""
    try:
        resolved = _resolve_repo_path(repo_path, task_id)
        file_ops = _get_file_ops(task_id)
        
        if not file_ops.exists(resolved / ".git"):
            return json.dumps({"error": f"Not a Git repository: {repo_path}"})
        
        # Determine range
        if from_tag and to_tag:
            range_spec = f"{from_tag}..{to_tag}"
        elif from_tag:
            range_spec = f"{from_tag}..HEAD"
        else:
            # Get last tag
            tag_result = _run_git_command(
                "git describe --tags --abbrev=0",
                str(resolved), task_id
            )
            if tag_result.get("success"):
                last_tag = tag_result.get("stdout", "").strip()
                range_spec = f"{last_tag}..HEAD"
            else:
                range_spec = "HEAD"
        
        # Get commits with conventional format
        log_result = _run_git_command(
            f"git log {range_spec} --pretty=format:'%h|%s|%an|%ad' --date=short --reverse",
            str(resolved), task_id
        )
        
        if not log_result.get("success"):
            return json.dumps({"error": f"Failed to get log: {log_result.get('error')}"})
        
        commits = []
        for line in log_result.get("stdout", "").strip().split('\n'):
            if line.strip():
                parts = line.split('|', 3)
                if len(parts) == 4:
                    commits.append({
                        "hash": parts[0],
                        "message": parts[1],
                        "author": parts[2],
                        "date": parts[3],
                    })
        
        if format == "json":
            return json.dumps({"commits": commits, "range": range_spec})
        
        # Parse conventional commits
        changelog = {}
        for commit in commits:
            msg = commit["message"]
            # Parse conventional commit: type(scope): description
            match = re.match(r'^(\w+)(?:\(([^)]+)\))?:\s*(.+)$', msg)
            if match:
                commit_type = match.group(1)
                scope = match.group(2)
                description = match.group(3)
            else:
                commit_type = "chore"
                scope = None
                description = msg
            
            if group_by_type:
                if commit_type not in changelog:
                    changelog[commit_type] = []
                changelog[commit_type].append({
                    "description": description,
                    "scope": scope,
                    "hash": commit["hash"],
                    "author": commit["author"],
                    "date": commit["date"],
                })
            else:
                if "all" not in changelog:
                    changelog["all"] = []
                changelog["all"].append({
                    "type": commit_type,
                    "description": description,
                    "scope": scope,
                    "hash": commit["hash"],
                    "author": commit["author"],
                    "date": commit["date"],
                })
        
        if format == "markdown":
            output = [f"# Changelog ({range_spec})\n"]
            
            type_order = ["feat", "fix", "perf", "refactor", "docs", "style", "test", "chore", "build", "ci", "revert"]
            for t in type_order:
                if t in changelog and changelog[t]:
                    output.append(f"## {t.capitalize()}\n")
                    for c in changelog[t]:
                        scope_str = f"({c['scope']})" if c['scope'] else ""
                        output.append(f"- {c['description']} {scope_str} [`{c['hash'][:7]}`]")
                    output.append("")
            
            # Any remaining types
            for t, items in changelog.items():
                if t not in type_order and items:
                    output.append(f"## {t.capitalize()}\n")
                    for c in items:
                        scope_str = f"({c['scope']})" if c['scope'] else ""
                        output.append(f"- {c['description']} {scope_str} [`{c['hash'][:7]}`]")
                    output.append("")
            
            return "\n".join(output)
        
        else:  # text
            output = [f"Changelog ({range_spec})\n"]
            for t, items in changelog.items():
                output.append(f"\n{t.upper()}:")
                for c in items:
                    scope_str = f"({c['scope']})" if c['scope'] else ""
                    output.append(f"  - {c['description']} {scope_str}")
            return "\n".join(output)
    
    except Exception as e:
        logger.exception("git_changelog error: %s", e)
        return json.dumps({"error": f"Changelog generation failed: {e}"})


# Register all tools
def _register_git_tools():
    """Register all git tools with the registry."""

    tools = [
        ("git_clone", "git", {
            "name": "git_clone",
            "description": "Clone a Git repository with authentication options",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "Repository URL"},
                    "destination": {"type": "string", "description": "Destination path", "default": None},
                    "branch": {"type": "string", "description": "Branch to clone", "default": None},
                    "depth": {"type": "integer", "description": "Shallow clone depth", "default": None},
                    "recursive": {"type": "boolean", "description": "Clone submodules recursively", "default": False},
                    "auth_token": {"type": "string", "description": "Authentication token for private repos", "default": None},
                },
                "required": ["url"],
            },
        }, git_clone, None, [], False, "📥", None),

        ("git_analyze", "git", {
            "name": "git_analyze",
            "description": "Analyze a Git repository (stats, contributors, history, branches)",
            "parameters": {
                "type": "object",
                "properties": {
                    "repo_path": {"type": "string", "description": "Repository path", "default": "."},
                    "include_stats": {"type": "boolean", "description": "Include basic stats", "default": True},
                    "include_contributors": {"type": "boolean", "description": "Include contributor info", "default": True},
                    "include_history": {"type": "boolean", "description": "Include commit history", "default": True},
                    "max_commits": {"type": "integer", "description": "Max commits to retrieve", "default": 100},
                },
                "required": [],
            },
        }, git_analyze, None, [], False, "📊", None),

        ("git_commit", "git", {
            "name": "git_commit",
            "description": "Create a Git commit with conventional message formatting",
            "parameters": {
                "type": "object",
                "properties": {
                    "repo_path": {"type": "string", "description": "Repository path", "default": "."},
                    "message": {"type": "string", "description": "Commit message", "default": ""},
                    "files": {"type": "array", "items": {"type": "string"}, "description": "Files to stage", "default": None},
                    "all_changes": {"type": "boolean", "description": "Stage all changes", "default": False},
                    "sign": {"type": "boolean", "description": "Sign commit with GPG", "default": False},
                    "conventional": {"type": "boolean", "description": "Use conventional commit format", "default": True},
                },
                "required": [],
            },
        }, git_commit, None, [], False, "💾", None),

        ("git_branch", "git", {
            "name": "git_branch",
            "description": "Manage Git branches (list, create, delete, switch, rename)",
            "parameters": {
                "type": "object",
                "properties": {
                    "repo_path": {"type": "string", "description": "Repository path", "default": "."},
                    "action": {"type": "string", "enum": ["list", "create", "delete", "switch", "rename"], "default": "list"},
                    "branch_name": {"type": "string", "description": "Branch name", "default": None},
                    "new_name": {"type": "string", "description": "New name for rename", "default": None},
                    "start_point": {"type": "string", "description": "Start point for new branch", "default": None},
                    "force": {"type": "boolean", "description": "Force delete", "default": False},
                },
                "required": [],
            },
        }, git_branch, None, [], False, "🌿", None),

        ("git_merge", "git", {
            "name": "git_merge",
            "description": "Merge branches with conflict detection",
            "parameters": {
                "type": "object",
                "properties": {
                    "repo_path": {"type": "string", "description": "Repository path", "default": "."},
                    "source_branch": {"type": "string", "description": "Branch to merge from"},
                    "target_branch": {"type": "string", "description": "Branch to merge into", "default": None},
                    "no_ff": {"type": "boolean", "description": "No fast-forward", "default": False},
                    "squash": {"type": "boolean", "description": "Squash merge", "default": False},
                    "strategy": {"type": "string", "description": "Merge strategy", "default": None},
                },
                "required": ["source_branch"],
            },
        }, git_merge, None, [], False, "🔀", None),

        ("git_conflict_explain", "git", {
            "name": "git_conflict_explain",
            "description": "Explain merge conflicts in repository or specific file",
            "parameters": {
                "type": "object",
                "properties": {
                    "repo_path": {"type": "string", "description": "Repository path", "default": "."},
                    "file_path": {"type": "string", "description": "Specific file to explain", "default": None},
                },
                "required": [],
            },
        }, git_conflict_explain, None, [], False, "⚔️", None),

        ("git_diff", "git", {
            "name": "git_diff",
            "description": "Show and summarize Git diffs",
            "parameters": {
                "type": "object",
                "properties": {
                    "repo_path": {"type": "string", "description": "Repository path", "default": "."},
                    "source": {"type": "string", "description": "Source revision", "default": None},
                    "target": {"type": "string", "description": "Target revision", "default": None},
                    "files": {"type": "array", "items": {"type": "string"}, "description": "Limit to files", "default": None},
                    "summary": {"type": "boolean", "description": "Show summary stats", "default": True},
                },
                "required": [],
            },
        }, git_diff, None, [], False, "📝", None),

        ("git_code_review", "git", {
            "name": "git_code_review",
            "description": "Automated code review on a branch",
            "parameters": {
                "type": "object",
                "properties": {
                    "repo_path": {"type": "string", "description": "Repository path", "default": "."},
                    "source_branch": {"type": "string", "description": "Branch to review"},
                    "target_branch": {"type": "string", "description": "Base branch", "default": "main"},
                    "focus_areas": {"type": "array", "items": {"type": "string"}, "description": "Focus areas", "default": None},
                },
                "required": ["source_branch"],
            },
        }, git_code_review, None, [], False, "👀", None),

        ("git_release", "git", {
            "name": "git_release",
            "description": "Create a release tag",
            "parameters": {
                "type": "object",
                "properties": {
                    "repo_path": {"type": "string", "description": "Repository path", "default": "."},
                    "version": {"type": "string", "description": "Version string"},
                    "tag_name": {"type": "string", "description": "Custom tag name", "default": None},
                    "message": {"type": "string", "description": "Tag message", "default": None},
                    "push": {"type": "boolean", "description": "Push tag to remote", "default": False},
                },
                "required": ["version"],
            },
        }, git_release, None, [], False, "🏷️", None),

        ("git_stats", "git", {
            "name": "git_stats",
            "description": "Get repository statistics",
            "parameters": {
                "type": "object",
                "properties": {
                    "repo_path": {"type": "string", "description": "Repository path", "default": "."},
                    "since": {"type": "string", "description": "Since date (ISO format)", "default": None},
                    "until": {"type": "string", "description": "Until date (ISO format)", "default": None},
                    "author": {"type": "string", "description": "Filter by author", "default": None},
                },
                "required": [],
            },
        }, git_stats, None, [], False, "📈", None),

        ("git_pr_prepare", "git", {
            "name": "git_pr_prepare",
            "description": "Prepare a pull request with generated description",
            "parameters": {
                "type": "object",
                "properties": {
                    "repo_path": {"type": "string", "description": "Repository path", "default": "."},
                    "source_branch": {"type": "string", "description": "Source branch"},
                    "target_branch": {"type": "string", "description": "Target branch", "default": "main"},
                    "title": {"type": "string", "description": "PR title", "default": None},
                    "body": {"type": "string", "description": "PR body", "default": None},
                    "draft": {"type": "boolean", "description": "Mark as draft", "default": False},
                },
                "required": ["source_branch"],
            },
        }, git_pr_prepare, None, [], False, "🔧", None),

        ("git_changelog", "git", {
            "name": "git_changelog",
            "description": "Generate changelog from Git history",
            "parameters": {
                "type": "object",
                "properties": {
                    "repo_path": {"type": "string", "description": "Repository path", "default": "."},
                    "from_tag": {"type": "string", "description": "Start tag", "default": None},
                    "to_tag": {"type": "string", "description": "End tag", "default": None},
                    "format": {"type": "string", "enum": ["markdown", "json", "text"], "default": "markdown"},
                    "group_by_type": {"type": "boolean", "description": "Group by commit type", "default": True},
                },
                "required": [],
            },
        }, git_changelog, None, [], False, "📋", None),
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
_register_git_tools()

__all__ = [
    "git_clone",
    "git_analyze",
    "git_commit",
    "git_branch",
    "git_merge",
    "git_conflict_explain",
    "git_diff",
    "git_code_review",
    "git_release",
    "git_stats",
    "git_pr_prepare",
    "git_changelog",
]

if __name__ == "__main__":
    print("Git tools loaded successfully")