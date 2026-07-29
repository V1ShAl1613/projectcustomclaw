#!/usr/bin/env python3
"""
Advanced Terminal Tools Module

Extends Hermes terminal with persistent shell sessions, environment profiles,
background job management, process monitoring, and real-time output streaming.

Tools:
- shell_session_create: Create persistent shell session
- shell_session_execute: Execute command in existing session
- shell_session_history: Get command history
- shell_session_env: Manage environment profiles
- shell_stream_output: Stream stdout/stderr in real-time
- shell_cancel: Cancel running command
- shell_background_job: Manage background jobs
- shell_process_monitor: Monitor process tree
- shell_timeout_manager: Advanced timeout handling
"""

import json
import logging
import os
import signal
import subprocess
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from tools.registry import registry
from tools.terminal_tool import (
    terminal_tool,
    FOREGROUND_MAX_TIMEOUT,
    record_session_cwd,
)

logger = logging.getLogger(__name__)


@dataclass
class ShellSession:
    """Represents a persistent shell session."""
    session_id: str
    created_at: float
    last_activity: float
    cwd: str
    env: Dict[str, str]
    history: List[Dict[str, Any]] = field(default_factory=list)
    process: Optional[subprocess.Popen] = None
    output_buffer: List[str] = field(default_factory=list)
    is_active: bool = True
    lock: threading.Lock = field(default_factory=threading.Lock)


@dataclass
class BackgroundJob:
    """Represents a background job."""
    job_id: str
    session_id: str
    command: str
    started_at: float
    status: str
    process: Optional[subprocess.Popen] = None
    output: List[str] = field(default_factory=list)
    exit_code: Optional[int] = None


# Global state for shell sessions and background jobs
_sessions: Dict[str, ShellSession] = {}
_sessions_lock = threading.Lock()
_jobs: Dict[str, BackgroundJob] = {}
_jobs_lock = threading.Lock()
_stream_subscribers: Dict[str, List[callable]] = {}
_stream_lock = threading.Lock()


def _get_session(session_id: str) -> Optional[ShellSession]:
    """Get a shell session by ID."""
    with _sessions_lock:
        return _sessions.get(session_id)


def _create_session(
    cwd: Optional[str] = None,
    env: Optional[Dict[str, str]] = None,
    session_id: Optional[str] = None
) -> ShellSession:
    """Create a new shell session."""
    if session_id is None:
        session_id = str(uuid.uuid4())[:8]
    
    if cwd is None:
        cwd = os.getcwd()
    
    session_env = os.environ.copy()
    if env:
        session_env.update(env)
    
    session = ShellSession(
        session_id=session_id,
        created_at=time.time(),
        last_activity=time.time(),
        cwd=cwd,
        env=session_env,
    )
    
    with _sessions_lock:
        _sessions[session_id] = session
    
    return session


def _update_session_activity(session_id: str) -> None:
    """Update last activity timestamp for a session."""
    with _sessions_lock:
        if session_id in _sessions:
            _sessions[session_id].last_activity = time.time()


def _cleanup_inactive_sessions(max_age_seconds: int = 3600) -> int:
    """Clean up sessions inactive for more than max_age_seconds."""
    cleaned = 0
    now = time.time()
    with _sessions_lock:
        to_remove = [
            sid for sid, sess in _sessions.items()
            if now - sess.last_activity > max_age_seconds and not sess.process
        ]
        for sid in to_remove:
            del _sessions[sid]
            cleaned += 1
    return cleaned


def shell_session_create(
    cwd: Optional[str] = None,
    env: Optional[Dict[str, str]] = None,
    session_id: Optional[str] = None,
    shell: str = "bash",
    task_id: str = "default",
) -> str:
    """Create a persistent shell session.
    
    Args:
        cwd: Working directory for the session (default: current directory)
        env: Environment variables to set in the session
        session_id: Optional custom session ID (auto-generated if not provided)
        shell: Shell to use (bash, zsh, fish, etc.)
        task_id: Task identifier for workspace resolution
        
    Returns:
        JSON string with session details
    """
    try:
        session = _create_session(cwd=cwd, env=env, session_id=session_id)
        session.env["SHELL"] = f"/bin/{shell}"
        
        # Record initial cwd
        from tools.terminal_tool import record_session_cwd
        record_session_cwd(session.session_id, session.cwd)
        
        return json.dumps({
            "success": True,
            "session_id": session.session_id,
            "cwd": session.cwd,
            "shell": shell,
            "created_at": session.created_at,
            "message": f"Created shell session {session.session_id}"
        })
    except Exception as e:
        logger.exception("Failed to create shell session")
        return json.dumps({"error": str(e)})


def shell_session_execute(
    session_id: str,
    command: str,
    timeout: int = 120,
    stream: bool = False,
    task_id: str = "default",
) -> str:
    """Execute a command in an existing shell session.
    
    Args:
        session_id: ID of the session to execute in
        command: Command to execute
        timeout: Command timeout in seconds
        stream: Whether to stream output in real-time
        task_id: Task identifier for workspace resolution
        
    Returns:
        JSON string with command output
    """
    session = _get_session(session_id)
    if not session:
        return json.dumps({"error": f"Session not found: {session_id}"})
    
    try:
        with session.lock:
            session.last_activity = time.time()
            
            # Record command in history
            history_entry = {
                "command": command,
                "timestamp": time.time(),
                "cwd": session.cwd,
            }
            session.history.append(history_entry)
            if len(session.history) > 1000:
                session.history = session.history[-1000:]
            
            # Build full command with session context
            full_cmd = f"cd {session.cwd} && {command}"
            
            # Use terminal_tool for execution
            result = terminal_tool(
                command=full_cmd,
                background=False,
                timeout=timeout,
                notify_on_complete=False,
                task_id=task_id,
            )
            
            # Update cwd from result if available
            try:
                result_data = json.loads(result)
                if "cwd" in result_data:
                    session.cwd = result_data["cwd"]
                    from tools.terminal_tool import record_session_cwd
                    record_session_cwd(session_id, session.cwd)
            except Exception:
                pass
            
            history_entry["result"] = result
            return result
            
    except Exception as e:
        logger.exception("Failed to execute in shell session")
        return json.dumps({"error": str(e)})


def shell_session_history(
    session_id: str,
    limit: int = 50,
    task_id: str = "default",
) -> str:
    """Get command history for a shell session.
    
    Args:
        session_id: ID of the session
        limit: Maximum number of history entries to return
        task_id: Task identifier
        
    Returns:
        JSON string with history entries
    """
    session = _get_session(session_id)
    if not session:
        return json.dumps({"error": f"Session not found: {session_id}"})
    
    history = session.history[-limit:] if limit > 0 else session.history
    return json.dumps({
        "session_id": session_id,
        "history": history,
        "total_commands": len(session.history),
    })


def shell_session_env(
    session_id: str,
    action: str = "get",
    env_vars: Optional[Dict[str, str]] = None,
    task_id: str = "default",
) -> str:
    """Manage environment variables for a shell session.
    
    Args:
        session_id: ID of the session
        action: Action to perform (get, set, unset, list)
        env_vars: Environment variables to set/unset
        task_id: Task identifier
        
    Returns:
        JSON string with environment variables
    """
    session = _get_session(session_id)
    if not session:
        return json.dumps({"error": f"Session not found: {session_id}"})
    
    try:
        if action == "get":
            return json.dumps({"session_id": session_id, "env": session.env})
        
        elif action == "set":
            if not env_vars:
                return json.dumps({"error": "env_vars required for set action"})
            session.env.update(env_vars)
            return json.dumps({
                "success": True,
                "session_id": session_id,
                "set": list(env_vars.keys())
            })
        
        elif action == "unset":
            if not env_vars:
                return json.dumps({"error": "env_vars required for unset action"})
            removed = []
            for key in env_vars:
                if key in session.env:
                    del session.env[key]
                    removed.append(key)
            return json.dumps({
                "success": True,
                "session_id": session_id,
                "removed": removed
            })
        
        elif action == "list":
            return json.dumps({
                "session_id": session_id,
                "env": session.env
            })
        
        else:
            return json.dumps({"error": f"Unknown action: {action}"})
            
    except Exception as e:
        logger.exception("Failed to manage session environment")
        return json.dumps({"error": str(e)})


def shell_session_close(
    session_id: str,
    task_id: str = "default",
) -> str:
    """Close a shell session.
    
    Args:
        session_id: ID of the session to close
        task_id: Task identifier
        
    Returns:
        JSON string with result
    """
    with _sessions_lock:
        session = _sessions.pop(session_id, None)
    
    if not session:
        return json.dumps({"error": f"Session not found: {session_id}"})
    
    # Terminate any running process
    if session.process and session.process.poll() is None:
        try:
            session.process.terminate()
            session.process.wait(timeout=5)
        except Exception:
            try:
                session.process.kill()
            except Exception:
                pass
    
    return json.dumps({
        "success": True,
        "session_id": session_id,
        "message": f"Closed session {session_id}"
    })


def shell_stream_output(
    session_id: str,
    command: str,
    timeout: int = 300,
    task_id: str = "default",
) -> str:
    """Stream command output in real-time.
    
    Args:
        session_id: ID of the session
        command: Command to execute
        timeout: Command timeout in seconds
        task_id: Task identifier
        
    Returns:
        JSON string with streaming info
    """
    session = _get_session(session_id)
    if not session:
        return json.dumps({"error": f"Session not found: {session_id}"})
    
    try:
        stream_id = f"{session_id}:{uuid.uuid4().hex[:8]}"
        
        def stream_reader():
            full_cmd = f"cd {session.cwd} && {command}"
            process = subprocess.Popen(
                full_cmd,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                env=session.env,
            )
            
            with _stream_lock:
                _stream_subscribers[stream_id] = []
            
            try:
                for line in iter(process.stdout.readline, ''):
                    if not line:
                        break
                    line = line.rstrip('\n')
                    session.output_buffer.append(line)
                    with _stream_lock:
                        for callback in _stream_subscribers.get(stream_id, []):
                            try:
                                callback(line)
                            except Exception:
                                pass
                process.wait()
            except Exception as e:
                logger.exception("Stream reader error")
            finally:
                with _stream_lock:
                    _stream_subscribers.pop(stream_id, None)
        
        thread = threading.Thread(target=stream_reader, daemon=True)
        thread.start()
        
        return json.dumps({
            "success": True,
            "stream_id": stream_id,
            "message": "Stream started. Use shell_stream_read to read output."
        })
        
    except Exception as e:
        logger.exception("Failed to start stream")
        return json.dumps({"error": str(e)})


def shell_stream_read(
    stream_id: str,
    wait: bool = True,
    timeout: float = 5.0,
    task_id: str = "default",
) -> str:
    """Read from an active stream.
    
    Args:
        stream_id: Stream ID from shell_stream_output
        wait: Whether to wait for new output
        timeout: Max time to wait for output
        task_id: Task identifier
        
    Returns:
        JSON string with stream output
    """
    # This is a simplified version - in production would use proper async/queue
    return json.dumps({
        "stream_id": stream_id,
        "output": [],
        "wait": wait,
        "note": "Stream reading requires websocket/SSE connection for real-time"
    })


def shell_cancel(
    session_id: str,
    task_id: str = "default",
) -> str:
    """Cancel a running command in a session.
    
    Args:
        session_id: ID of the session
        task_id: Task identifier
        
    Returns:
        JSON string with result
    """
    session = _get_session(session_id)
    if not session:
        return json.dumps({"error": f"Session not found: {session_id}"})
    
    try:
        if session.process and session.process.poll() is None:
            session.process.send_signal(signal.SIGINT)
            try:
                session.process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                session.process.kill()
                session.process.wait()
            return json.dumps({
                "success": True,
                "message": "Command cancelled"
            })
        return json.dumps({
            "success": False,
            "message": "No running command to cancel"
        })
    except Exception as e:
        logger.exception("Failed to cancel command")
        return json.dumps({"error": str(e)})


def shell_background_job(
    action: str = "list",
    session_id: Optional[str] = None,
    command: Optional[str] = None,
    job_id: Optional[str] = None,
    timeout: int = 3600,
    task_id: str = "default",
) -> str:
    """Manage background jobs.
    
    Args:
        action: Action (create, list, get, wait, kill, remove)
        session_id: Session to run job in (required for create)
        command: Command to run (required for create)
        job_id: Job ID (for get/wait/kill/remove)
        timeout: Job timeout in seconds
        task_id: Task identifier
        
    Returns:
        JSON string with result
    """
    try:
        if action == "create":
            if not session_id or not command:
                return json.dumps({"error": "session_id and command required for create"})
            
            session = _get_session(session_id)
            if not session:
                return json.dumps({"error": f"Session not found: {session_id}"})
            
            job_id = job_id or str(uuid.uuid4())[:8]
            
            def job_runner():
                full_cmd = f"cd {session.cwd} && {command}"
                process = subprocess.Popen(
                    full_cmd,
                    shell=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1,
                    env=session.env,
                )
                
                job = BackgroundJob(
                    job_id=job_id,
                    session_id=session_id,
                    command=command,
                    started_at=time.time(),
                    status="running",
                    process=process,
                )
                
                with _jobs_lock:
                    _jobs[job_id] = job
                
                try:
                    for line in iter(process.stdout.readline, ''):
                        if not line:
                            break
                        job.output.append(line.rstrip('\n'))
                        if len(job.output) > 10000:
                            job.output = job.output[-10000:]
                    
                    process.wait()
                    job.exit_code = process.returncode
                    job.status = "completed" if job.exit_code == 0 else "failed"
                except Exception as e:
                    job.status = "error"
                    job.output.append(f"Error: {e}")
                finally:
                    with _jobs_lock:
                        _jobs[job_id] = job
            
            thread = threading.Thread(target=job_runner, daemon=True)
            thread.start()
            
            return json.dumps({
                "success": True,
                "job_id": job_id,
                "status": "running",
                "message": f"Started background job {job_id}"
            })
        
        elif action == "list":
            with _jobs_lock:
                jobs = [
                    {
                        "job_id": j.job_id,
                        "session_id": j.session_id,
                        "command": j.command,
                        "started_at": j.started_at,
                        "status": j.status,
                        "exit_code": j.exit_code,
                    }
                    for j in _jobs.values()
                ]
            return json.dumps({"jobs": jobs})
        
        elif action == "get":
            if not job_id:
                return json.dumps({"error": "job_id required for get"})
            with _jobs_lock:
                job = _jobs.get(job_id)
            if not job:
                return json.dumps({"error": f"Job not found: {job_id}"})
            return json.dumps({
                "job_id": job.job_id,
                "session_id": job.session_id,
                "command": job.command,
                "started_at": job.started_at,
                "status": job.status,
                "exit_code": job.exit_code,
                "output": job.output[-100:] if job.output else [],
            })
        
        elif action == "wait":
            if not job_id:
                return json.dumps({"error": "job_id required for wait"})
            start = time.time()
            while time.time() - start < timeout:
                with _jobs_lock:
                    job = _jobs.get(job_id)
                if job and job.status in ("completed", "failed", "error"):
                    return json.dumps({
                        "job_id": job.job_id,
                        "status": job.status,
                        "exit_code": job.exit_code,
                        "output": job.output[-100:] if job.output else [],
                    })
                time.sleep(0.5)
            return json.dumps({"error": "Timeout waiting for job"})
        
        elif action == "kill":
            if not job_id:
                return json.dumps({"error": "job_id required for kill"})
            with _jobs_lock:
                job = _jobs.get(job_id)
            if not job:
                return json.dumps({"error": f"Job not found: {job_id}"})
            if job.process and job.process.poll() is None:
                job.process.terminate()
                try:
                    job.process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    job.process.kill()
                    job.process.wait()
                job.status = "killed"
                return json.dumps({"success": True, "message": f"Killed job {job_id}"})
            return json.dumps({"error": "Job not running"})
        
        elif action == "remove":
            if not job_id:
                return json.dumps({"error": "job_id required for remove"})
            with _jobs_lock:
                _jobs.pop(job_id, None)
            return json.dumps({"success": True, "message": f"Removed job {job_id}"})
        
        else:
            return json.dumps({"error": f"Unknown action: {action}"})
            
    except Exception as e:
        logger.exception("Failed to manage background job")
        return json.dumps({"error": str(e)})


def shell_process_monitor(
    action: str = "list",
    pid: Optional[int] = None,
    task_id: str = "default",
) -> str:
    """Monitor process tree.
    
    Args:
        action: Action (list, tree, info, kill)
        pid: Process ID (required for tree, info, kill)
        task_id: Task identifier
        
    Returns:
        JSON string with process info
    """
    try:
        import psutil
    except ImportError:
        return json.dumps({"error": "psutil not installed. Run: pip install psutil"})
    
    try:
        if action == "list":
            processes = []
            for proc in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_percent', 'create_time']):
                try:
                    info = proc.info
                    info['create_time'] = info['create_time']
                    processes.append(info)
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
            return json.dumps({"processes": processes[:100]})
        
        elif action == "tree":
            if not pid:
                return json.dumps({"error": "pid required for tree"})
            try:
                parent = psutil.Process(pid)
                children = parent.children(recursive=True)
                tree = {
                    "pid": parent.pid,
                    "name": parent.name(),
                    "cmdline": parent.cmdline(),
                    "children": [
                        {
                            "pid": c.pid,
                            "name": c.name(),
                            "cmdline": c.cmdline(),
                            "cpu_percent": c.cpu_percent(),
                            "memory_percent": c.memory_percent(),
                        }
                        for c in children
                    ]
                }
                return json.dumps(tree)
            except psutil.NoSuchProcess:
                return json.dumps({"error": f"Process not found: {pid}"})
        
        elif action == "info":
            if not pid:
                return json.dumps({"error": "pid required for info"})
            try:
                proc = psutil.Process(pid)
                return json.dumps({
                    "pid": proc.pid,
                    "name": proc.name(),
                    "cmdline": proc.cmdline(),
                    "status": proc.status(),
                    "cpu_percent": proc.cpu_percent(),
                    "memory_percent": proc.memory_percent(),
                    "memory_info": proc.memory_info()._asdict() if proc.memory_info() else {},
                    "create_time": proc.create_time(),
                    "num_threads": proc.num_threads(),
                    "open_files": len(proc.open_files()) if proc.open_files() else 0,
                    "connections": len(proc.connections()) if proc.connections() else 0,
                })
            except psutil.NoSuchProcess:
                return json.dumps({"error": f"Process not found: {pid}"})
        
        elif action == "kill":
            if not pid:
                return json.dumps({"error": "pid required for kill"})
            try:
                proc = psutil.Process(pid)
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except psutil.TimeoutExpired:
                    proc.kill()
                    proc.wait()
                return json.dumps({"success": True, "message": f"Killed process {pid}"})
            except psutil.NoSuchProcess:
                return json.dumps({"error": f"Process not found: {pid}"})
        
        else:
            return json.dumps({"error": f"Unknown action: {action}"})
            
    except Exception as e:
        logger.exception("Process monitor error")
        return json.dumps({"error": str(e)})


def shell_timeout_manager(
    action: str = "set",
    timeout: int = 120,
    session_id: Optional[str] = None,
    task_id: str = "default",
) -> str:
    """Advanced timeout management for shell operations.
    
    Args:
        action: Action (set, get, extend, reset)
        timeout: Timeout value in seconds
        session_id: Session ID (required for set/extend)
        task_id: Task identifier
        
    Returns:
        JSON string with timeout info
    """
    # This integrates with terminal_tool's timeout handling
    # For session-specific timeouts, we store them in session metadata
    
    if action == "set":
        if not session_id:
            return json.dumps({"error": "session_id required for set"})
        session = _get_session(session_id)
        if not session:
            return json.dumps({"error": f"Session not found: {session_id}"})
        session.env["TERMINAL_TIMEOUT"] = str(min(timeout, FOREGROUND_MAX_TIMEOUT))
        return json.dumps({
            "success": True,
            "session_id": session_id,
            "timeout": session.env["TERMINAL_TIMEOUT"]
        })
    
    elif action == "get":
        if not session_id:
            return json.dumps({"error": "session_id required for get"})
        session = _get_session(session_id)
        if not session:
            return json.dumps({"error": f"Session not found: {session_id}"})
        return json.dumps({
            "session_id": session_id,
            "timeout": session.env.get("TERMINAL_TIMEOUT", str(FOREGROUND_MAX_TIMEOUT))
        })
    
    elif action == "extend":
        if not session_id:
            return json.dumps({"error": "session_id required for extend"})
        session = _get_session(session_id)
        if not session:
            return json.dumps({"error": f"Session not found: {session_id}"})
        current = int(session.env.get("TERMINAL_TIMEOUT", FOREGROUND_MAX_TIMEOUT))
        new_timeout = min(current + timeout, FOREGROUND_MAX_TIMEOUT)
        session.env["TERMINAL_TIMEOUT"] = str(new_timeout)
        return json.dumps({
            "success": True,
            "session_id": session_id,
            "old_timeout": current,
            "new_timeout": new_timeout
        })
    
    elif action == "reset":
        if not session_id:
            return json.dumps({"error": "session_id required for reset"})
        session = _get_session(session_id)
        if not session:
            return json.dumps({"error": f"Session not found: {session_id}"})
        session.env["TERMINAL_TIMEOUT"] = str(FOREGROUND_MAX_TIMEOUT)
        return json.dumps({
            "success": True,
            "session_id": session_id,
            "timeout": FOREGROUND_MAX_TIMEOUT
        })
    
    else:
        return json.dumps({"error": f"Unknown action: {action}"})


def shell_session_list(task_id: str = "default") -> str:
    """List all active shell sessions."""
    with _sessions_lock:
        sessions = [
            {
                "session_id": s.session_id,
                "cwd": s.cwd,
                "created_at": s.created_at,
                "last_activity": s.last_activity,
                "history_length": len(s.history),
                "is_active": s.is_active,
            }
            for s in _sessions.values()
        ]
    return json.dumps({"sessions": sessions})


def _register_terminal_advanced_tools():
    """Register all terminal advanced tools."""
    tools = [
        ("shell_session_create", shell_session_create, "Create a persistent shell session", {}),
        ("shell_session_execute", shell_session_execute, "Execute command in existing shell session", {}),
        ("shell_session_history", shell_session_history, "Get command history for a shell session", {}),
        ("shell_session_env", shell_session_env, "Manage environment variables for a shell session", {}),
        ("shell_session_close", shell_session_close, "Close a shell session", {}),
        ("shell_session_list", shell_session_list, "List all active shell sessions", {}),
        ("shell_stream_output", shell_stream_output, "Stream command output in real-time", {}),
        ("shell_cancel", shell_cancel, "Cancel a running command in a session", {}),
        ("shell_background_job", shell_background_job, "Manage background jobs", {}),
        ("shell_process_monitor", shell_process_monitor, "Monitor process tree", {}),
        ("shell_timeout_manager", shell_timeout_manager, "Advanced timeout management", {}),
    ]
    
    def make_handler(f):
        return lambda args, **kw: f(**args, **kw)
    
    for name, func, desc, schema in tools:
        registry.register(
            name=name,
            toolset="terminal_advanced",
            schema={"name": name, "description": desc, "parameters": schema},
            handler=make_handler(func),
            check_fn=lambda: True,
            requires_env=[],
            is_async=False,
            description=desc,
        )


_register_terminal_advanced_tools()