#!/usr/bin/env python3
"""
Enhanced Logging Tools Module

Provides advanced logging capabilities:
- Structured logging (JSON, key-value)
- Colored terminal output
- Worker/container log aggregation
- Tool execution audit trails
- Log streaming and filtering
"""

import json
import logging
import os
import sys
import threading
import time
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Callable

from tools.registry import registry
from tools.terminal_tool import terminal_tool

logger = logging.getLogger(__name__)

# Log formatters
class JSONFormatter(logging.Formatter):
    """JSON log formatter."""
    def format(self, record: logging.LogRecord) -> str:
        log_obj = {
            "timestamp": datetime.fromtimestamp(record.created).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }
        
        # Add extra fields
        for key, value in record.__dict__.items():
            if key not in ("name", "msg", "args", "created", "filename", "funcName",
                          "levelname", "levelno", "lineno", "module", "msecs",
                          "message", "pathname", "process", "processName",
                          "relativeCreated", "thread", "threadName", "exc_info",
                          "exc_text", "stack_info", "getMessage"):
                log_obj[key] = value
        
        if record.exc_info:
            log_obj["exception"] = self.formatException(record.exc_info)
        
        return json.dumps(log_obj)


class ColoredFormatter(logging.Formatter):
    """Colored terminal log formatter."""
    COLORS = {
        "DEBUG": "\033[36m",      # Cyan
        "INFO": "\033[32m",       # Green
        "WARNING": "\033[33m",    # Yellow
        "ERROR": "\033[31m",      # Red
        "CRITICAL": "\033[35m",   # Magenta
        "RESET": "\033[0m",
    }
    
    def format(self, record: logging.LogRecord) -> str:
        color = self.COLORS.get(record.levelname, "")
        reset = self.COLORS["RESET"]
        
        formatted = super().format(record)
        return f"{color}{formatted}{reset}"


# Global log storage for audit trail
_audit_logs: List[Dict] = []
_audit_lock = threading.Lock()
_max_audit_logs = 10000

# Log subscribers for streaming
_log_subscribers: List[Callable] = []
_subscriber_lock = threading.Lock()


def _add_audit_log(entry: Dict) -> None:
    """Add entry to audit log."""
    with _audit_lock:
        _audit_logs.append(entry)
        if len(_audit_logs) > _max_audit_logs:
            _audit_logs.pop(0)


def _notify_subscribers(entry: Dict) -> None:
    """Notify log subscribers."""
    with _subscriber_lock:
        for callback in _log_subscribers:
            try:
                callback(entry)
            except Exception:
                pass


class StructuredLogger:
    """Structured logger with multiple outputs."""
    
    def __init__(self, name: str):
        self.logger = logging.getLogger(name)
        self._context: Dict = {}
    
    def bind(self, **kwargs) -> "StructuredLogger":
        """Bind context to logger."""
        new_logger = StructuredLogger(self.logger.name)
        new_logger.logger = self.logger
        new_logger._context = {**self._context, **kwargs}
        return new_logger
    
    def _log(self, level: int, message: str, **kwargs) -> None:
        extra = {**self._context, **kwargs}
        self.logger.log(level, message, extra=extra)
        
        # Add to audit log
        entry = {
            "timestamp": datetime.now().isoformat(),
            "level": logging.getLevelName(level),
            "logger": self.logger.name,
            "message": message,
            **extra,
        }
        _add_audit_log(entry)
        _notify_subscribers(entry)
    
    def debug(self, message: str, **kwargs) -> None:
        self._log(logging.DEBUG, message, **kwargs)
    
    def info(self, message: str, **kwargs) -> None:
        self._log(logging.INFO, message, **kwargs)
    
    def warning(self, message: str, **kwargs) -> None:
        self._log(logging.WARNING, message, **kwargs)
    
    def error(self, message: str, **kwargs) -> None:
        self._log(logging.ERROR, message, **kwargs)
    
    def critical(self, message: str, **kwargs) -> None:
        self._log(logging.CRITICAL, message, **kwargs)


def structured_log(
    message: str,
    level: str = "info",
    logger_name: str = "hermes.structured",
    context: Optional[Dict] = None,
    task_id: str = "default",
) -> str:
    """Log a structured message.
    
    Args:
        message: Log message
        level: Log level (debug, info, warning, error, critical)
        logger_name: Logger name
        context: Additional context fields
        task_id: Task identifier
        
    Returns:
        JSON string with result
    """
    try:
        log = StructuredLogger(logger_name)
        if context:
            log = log.bind(**context)
        
        level_map = {
            "debug": logging.DEBUG,
            "info": logging.INFO,
            "warning": logging.WARNING,
            "error": logging.ERROR,
            "critical": logging.CRITICAL,
        }
        log_level = level_map.get(level.lower(), logging.INFO)
        log._log(log_level, message)
        
        return json.dumps({"success": True, "logged": True})
    except Exception as e:
        return json.dumps({"error": str(e)})


def json_log(
    message: str,
    level: str = "info",
    logger_name: str = "hermes.json",
    fields: Optional[Dict] = None,
    task_id: str = "default",
) -> str:
    """Log as JSON to stdout.
    
    Args:
        message: Log message
        level: Log level
        logger_name: Logger name
        fields: Additional fields
        task_id: Task identifier
        
    Returns:
        JSON string
    """
    log_entry = {
        "timestamp": datetime.now().isoformat(),
        "level": level.upper(),
        "logger": logger_name,
        "message": message,
    }
    if fields:
        log_entry.update(fields)
    
    print(json.dumps(log_entry), flush=True)
    return json.dumps({"success": True, "logged": True})


def colored_log(
    message: str,
    level: str = "info",
    color: Optional[str] = None,
    task_id: str = "default",
) -> str:
    """Log with color to terminal.
    
    Args:
        message: Log message
        level: Log level
        color: Explicit color (red, green, yellow, blue, magenta, cyan)
        task_id: Task identifier
        
    Returns:
        JSON string
    """
    colors = {
        "red": "\033[31m",
        "green": "\033[32m",
        "yellow": "\033[33m",
        "blue": "\033[34m",
        "magenta": "\033[35m",
        "cyan": "\033[36m",
        "reset": "\033[0m",
    }
    
    level_colors = {
        "debug": "cyan",
        "info": "green",
        "warning": "yellow",
        "error": "red",
        "critical": "magenta",
    }
    
    used_color = colors.get(color or level_colors.get(level.lower(), "reset"), "")
    reset = colors["reset"]
    
    print(f"{used_color}{message}{reset}", flush=True)
    return json.dumps({"success": True, "logged": True})


def worker_logs(
    action: str = "list",
    worker_id: Optional[str] = None,
    container_id: Optional[str] = None,
    lines: int = 100,
    follow: bool = False,
    task_id: str = "default",
) -> str:
    """Get worker/container logs.
    
    Args:
        action: Action (list, get, stream)
        worker_id: Worker identifier
        container_id: Container identifier
        lines: Number of lines to retrieve
        follow: Follow log output
        task_id: Task identifier
        
    Returns:
        JSON string with logs
    """
    try:
        if action == "list":
            # List available workers/containers
            cmd = "docker ps --format '{{.ID}} {{.Names}} {{.Status}}'"
            result = terminal_tool(command=cmd, timeout=30, task_id=task_id)
            return result
        
        elif action == "get":
            if container_id:
                cmd = f"docker logs --tail {lines} {container_id}"
            elif worker_id:
                # Find container by worker ID
                cmd = f"docker ps --filter 'label=hermes.worker={worker_id}' --format '{{.ID}}'"
                result = terminal_tool(command=cmd, timeout=30, task_id=task_id)
                data = json.loads(result)
                if data.get("stdout"):
                    container = data["stdout"].strip().split("\n")[0]
                    cmd = f"docker logs --tail {lines} {container}"
                else:
                    return json.dumps({"error": f"No container found for worker {worker_id}"})
            else:
                return json.dumps({"error": "worker_id or container_id required"})
            
            result = terminal_tool(command=cmd, timeout=30, task_id=task_id)
            return result
        
        elif action == "stream":
            if not container_id:
                return json.dumps({"error": "container_id required for streaming"})
            cmd = f"docker logs -f --tail {lines} {container_id}"
            result = terminal_tool(command=cmd, background=True, task_id=task_id)
            return result
        
        else:
            return json.dumps({"error": f"Unknown action: {action}"})
            
    except Exception as e:
        return json.dumps({"error": str(e)})


def tool_execution_logs(
    action: str = "get",
    tool_name: Optional[str] = None,
    task_id: Optional[str] = None,
    limit: int = 100,
    task_id_param: str = "default",
) -> str:
    """Get tool execution audit logs.
    
    Args:
        action: Action (get, clear, stats)
        tool_name: Filter by tool name
        task_id: Filter by task ID
        limit: Maximum entries
        task_id_param: Task identifier parameter
        
    Returns:
        JSON string with logs
    """
    with _audit_lock:
        logs = list(_audit_logs)
    
    # Filter
    if tool_name:
        logs = [l for l in logs if l.get("tool_name") == tool_name or l.get("name") == tool_name]
    if task_id:
        logs = [l for l in logs if l.get("task_id") == task_id]
    
    if action == "get":
        return json.dumps({
            "logs": logs[-limit:],
            "total": len(logs),
        })
    elif action == "clear":
        with _audit_lock:
            _audit_logs.clear()
        return json.dumps({"success": True, "message": "Audit logs cleared"})
    elif action == "stats":
        tool_counts = {}
        level_counts = {}
        for log in logs:
            tool = log.get("tool_name") or log.get("name", "unknown")
            level = log.get("level", "unknown")
            tool_counts[tool] = tool_counts.get(tool, 0) + 1
            level_counts[level] = level_counts.get(level, 0) + 1
        
        return json.dumps({
            "total": len(logs),
            "by_tool": tool_counts,
            "by_level": level_counts,
        })
    else:
        return json.dumps({"error": f"Unknown action: {action}"})


def log_stream_subscribe(
    callback: str = "print",
    filter_level: Optional[str] = None,
    filter_logger: Optional[str] = None,
    task_id: str = "default",
) -> str:
    """Subscribe to log stream.
    
    Args:
        callback: Callback type (print, json, callback_name)
        filter_level: Minimum log level
        filter_logger: Logger name filter
        task_id: Task identifier
        
    Returns:
        JSON string with subscription info
    """
    # In a real implementation, this would set up a WebSocket or SSE connection
    # For now, return subscription info
    return json.dumps({
        "success": True,
        "subscription_id": f"sub_{int(time.time() * 1000)}",
        "message": "Log streaming requires WebSocket/SSE connection. Use the streaming API endpoint.",
    })


def configure_logging(
    level: str = "INFO",
    format: str = "json",
    output: str = "stdout",
    file_path: Optional[str] = None,
    task_id: str = "default",
) -> str:
    """Configure logging system.
    
    Args:
        level: Log level
        format: Format (json, colored, simple)
        output: Output destination (stdout, stderr, file)
        file_path: File path if output is file
        task_id: Task identifier
        
    Returns:
        JSON string with configuration result
    """
    try:
        log_level = getattr(logging, level.upper(), logging.INFO)
        
        # Clear existing handlers
        root_logger = logging.getLogger()
        for handler in root_logger.handlers[:]:
            root_logger.removeHandler(handler)
        
        # Create formatter
        if format == "json":
            formatter = JSONFormatter()
        elif format == "colored":
            formatter = ColoredFormatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
        else:
            formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
        
        # Create handler
        if output == "file" and file_path:
            handler = logging.FileHandler(file_path)
        elif output == "stderr":
            handler = logging.StreamHandler(sys.stderr)
        else:
            handler = logging.StreamHandler(sys.stdout)
        
        handler.setFormatter(formatter)
        root_logger.addHandler(handler)
        root_logger.setLevel(log_level)
        
        return json.dumps({
            "success": True,
            "level": level,
            "format": format,
            "output": output,
        })
    except Exception as e:
        return json.dumps({"error": str(e)})


def get_log_stats(task_id: str = "default") -> str:
    """Get logging statistics."""
    with _audit_lock:
        total = len(_audit_logs)
        by_level = {}
        by_logger = {}
        
        for log in _audit_logs:
            level = log.get("level", "unknown")
            logger_name = log.get("logger", "unknown")
            by_level[level] = by_level.get(level, 0) + 1
            by_logger[logger_name] = by_logger.get(logger_name, 0) + 1
    
    return json.dumps({
        "total_logs": total,
        "by_level": by_level,
        "by_logger": by_logger,
        "max_logs": _max_audit_logs,
    })


def _register_logging_tools():
    """Register all logging tools."""
    tools = [
        ("structured_log", structured_log, "Structured logging with context"),
        ("json_log", json_log, "Log as JSON to stdout"),
        ("colored_log", colored_log, "Colored terminal logging"),
        ("worker_logs", worker_logs, "Get worker/container logs"),
        ("tool_execution_logs", tool_execution_logs, "Get tool execution audit logs"),
        ("configure_logging", configure_logging, "Configure logging system"),
        ("get_log_stats", get_log_stats, "Get logging statistics"),
    ]
    
    for name, func, desc in tools:
        registry.register(
            name=name,
            toolset="logging_enhanced",
            schema={"name": name, "description": desc, "parameters": {"type": "object", "properties": {}}},
            handler=func,
            check_fn=lambda: True,
            description=desc,
        )


_register_logging_tools()