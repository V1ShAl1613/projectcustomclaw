#!/usr/bin/env python3
"""
Advanced Filesystem Tools Module

Extends Hermes with comprehensive filesystem operations:
- read/write/edit/rename/move/copy/delete
- recursive search with regex/glob
- file watching
- binary file handling
- archive extraction/creation
- checksum generation
- workspace indexing

All operations respect workspace boundaries and use existing Hermes
path resolution, terminal environments, and permission model.
"""

import hashlib
import json
import logging
import os
import shutil
import subprocess
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Set
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler, FileSystemEvent

from tools.registry import registry
from tools.file_tools import (
    _resolve_path_for_task,
    _expand_tilde,
    _get_file_ops,
    _check_sensitive_path,
    _check_cross_profile_path,
    _is_internal_file_tool_content,
    _is_expected_write_exception,
)
from tools.file_operations import ShellFileOperations
from tools.binary_extensions import has_binary_extension

logger = logging.getLogger(__name__)

# Global file watcher state
_watchers: Dict[str, Observer] = {}
_watcher_lock = threading.Lock()
_watch_events: Dict[str, List[Dict]] = {}
_watch_events_lock = threading.Lock()

# Maximum file size for direct read (100MB)
MAX_DIRECT_READ_SIZE = 100 * 1024 * 1024

# Archive extensions
ARCHIVE_EXTENSIONS = {
    '.zip': 'zip',
    '.tar': 'tar',
    '.tar.gz': 'tar.gz',
    '.tgz': 'tar.gz',
    '.tar.bz2': 'tar.bz2',
    '.tbz2': 'tar.bz2',
    '.tar.xz': 'tar.xz',
    '.txz': 'tar.xz',
    '.gz': 'gzip',
    '.bz2': 'bzip2',
    '.xz': 'xz',
    '.7z': '7z',
    '.rar': 'rar',
}

# Checksum algorithms
CHECKSUM_ALGORITHMS = {
    'md5': hashlib.md5,
    'sha1': hashlib.sha1,
    'sha256': hashlib.sha256,
    'sha512': hashlib.sha512,
    'blake3': None,  # Requires blake3 package
}

try:
    import blake3
    CHECKSUM_ALGORITHMS['blake3'] = blake3.blake3
except ImportError:
    pass


class FileWatchHandler(FileSystemEventHandler):
    """Handler for file system events."""

    def __init__(self, task_id: str, watch_id: str):
        self.task_id = task_id
        self.watch_id = watch_id

    def on_any_event(self, event: FileSystemEvent):
        if event.is_directory:
            return
        with _watch_events_lock:
            if self.watch_id not in _watch_events:
                _watch_events[self.watch_id] = []
            _watch_events[self.watch_id].append({
                'event_type': event.event_type,
                'src_path': event.src_path,
                'dest_path': getattr(event, 'dest_path', None),
                'timestamp': time.time(),
            })
            # Keep only last 1000 events
            if len(_watch_events[self.watch_id]) > 1000:
                _watch_events[self.watch_id] = _watch_events[self.watch_id][-1000:]


def _get_watcher(task_id: str, watch_id: str) -> Optional[Observer]:
    """Get a file watcher by ID."""
    with _watcher_lock:
        return _watchers.get(f"{task_id}:{watch_id}")


def _register_watcher(task_id: str, watch_id: str, observer: Observer) -> None:
    """Register a file watcher."""
    with _watcher_lock:
        _watchers[f"{task_id}:{watch_id}"] = observer


def _unregister_watcher(task_id: str, watch_id: str) -> None:
    """Unregister a file watcher."""
    with _watcher_lock:
        _watchers.pop(f"{task_id}:{watch_id}", None)


def _resolve_path(path: str, task_id: str = "default") -> Path:
    """Resolve a path using Hermes path resolution."""
    return _resolve_path_for_task(path, task_id)


def _get_file_ops_for_task(task_id: str = "default") -> ShellFileOperations:
    """Get file operations for a task."""
    return _get_file_ops(task_id)


def _validate_write_path(path: str, task_id: str = "default") -> Optional[str]:
    """Validate a path for writing. Returns error message if invalid."""
    # Check sensitive paths
    error = _check_sensitive_path(path, task_id)
    if error:
        return error
    # Check cross-profile paths
    error = _check_cross_profile_path(path, task_id)
    if error:
        return error
    return None


def read_file_advanced(
    path: str,
    offset: int = 1,
    limit: int = 500,
    encoding: str = "utf-8",
    binary: bool = False,
    task_id: str = "default",
) -> str:
    """Read a file with advanced options."""
    try:
        resolved = _resolve_path(path, task_id)
        file_ops = _get_file_ops_for_task(task_id)

        if not file_ops.exists(resolved):
            return json.dumps({"error": f"File not found: {path}"})

        # Check if binary file
        if not binary and has_binary_extension(str(resolved)):
            return json.dumps({
                "error": f"Binary file detected: {path}. Use binary=true or vision_analyze for images."
            })

        stat = file_ops.stat(resolved)
        file_size = stat.st_size

        if binary:
            # Read binary file as base64
            import base64
            content = file_ops.read_bytes(resolved, offset=offset-1, limit=limit)
            encoded = base64.b64encode(content).decode('ascii')
            return json.dumps({
                "content": encoded,
                "encoding": "base64",
                "file_size": file_size,
                "bytes_read": len(content),
                "truncated": len(content) == limit and (offset - 1 + limit) < file_size,
            })

        # Text file reading
        if file_size > MAX_DIRECT_READ_SIZE and limit > 10000:
            return json.dumps({
                "error": f"File too large ({file_size} bytes). Use smaller limit or binary mode."
            })

        lines = file_ops.read_lines(resolved)
        total_lines = len(lines)
        end_line = min(offset + limit - 1, total_lines)
        page_lines = lines[offset - 1:end_line]

        content = file_ops._add_line_numbers("\n".join(page_lines), offset)

        return json.dumps({
            "content": content,
            "total_lines": total_lines,
            "file_size": file_size,
            "truncated": end_line < total_lines,
            "encoding": encoding,
        })

    except Exception as e:
        logger.exception("read_file_advanced error: %s", e)
        return json.dumps({"error": f"Read failed: {e}"})


def write_file_advanced(
    path: str,
    content: str,
    encoding: str = "utf-8",
    binary: bool = False,
    backup: bool = True,
    atomic: bool = True,
    permissions: Optional[str] = None,
    create_dirs: bool = True,
    task_id: str = "default",
) -> str:
    """Write a file with advanced options."""
    try:
        # Validate path
        error = _validate_write_path(path, task_id)
        if error:
            return json.dumps({"error": error})

        resolved = _resolve_path(path, task_id)
        file_ops = _get_file_ops_for_task(task_id)

        # Create parent directories
        if create_dirs:
            parent = resolved.parent
            if not file_ops.exists(parent):
                file_ops.makedirs(parent, exist_ok=True)

        # Backup existing file
        if backup and file_ops.exists(resolved):
            backup_path = resolved.with_suffix(resolved.suffix + f".bak.{int(time.time())}")
            file_ops.copy(resolved, backup_path)

        # Write content
        if binary:
            import base64
            try:
                decoded = base64.b64decode(content)
            except Exception as e:
                return json.dumps({"error": f"Invalid base64 content: {e}"})

            if atomic:
                # Write to temp file then rename
                temp_path = resolved.with_suffix(resolved.suffix + ".tmp")
                file_ops.write_bytes(temp_path, decoded)
                file_ops.rename(temp_path, resolved)
            else:
                file_ops.write_bytes(resolved, decoded)
        else:
            if atomic:
                temp_path = resolved.with_suffix(resolved.suffix + ".tmp")
                file_ops.write(temp_path, content)
                file_ops.rename(temp_path, resolved)
            else:
                file_ops.write(resolved, content)

        # Set permissions
        if permissions:
            try:
                mode = int(permissions, 8)
                file_ops.chmod(resolved, mode)
            except ValueError:
                return json.dumps({"error": f"Invalid permissions: {permissions}"})

        stat = file_ops.stat(resolved)
        return json.dumps({
            "success": True,
            "path": str(resolved),
            "size": stat.st_size,
            "backup": backup and file_ops.exists(resolved.with_suffix(resolved.suffix + ".bak.*")),
        })

    except Exception as e:
        logger.exception("write_file_advanced error: %s", e)
        return json.dumps({"error": f"Write failed: {e}"})


def edit_file(
    path: str,
    old_string: str,
    new_string: str,
    replace_all: bool = False,
    task_id: str = "default",
) -> str:
    """Edit a file by replacing text."""
    try:
        error = _validate_write_path(path, task_id)
        if error:
            return json.dumps({"error": error})

        resolved = _resolve_path(path, task_id)
        file_ops = _get_file_ops_for_task(task_id)

        if not file_ops.exists(resolved):
            return json.dumps({"error": f"File not found: {path}"})

        content = file_ops.read(resolved)
        if old_string not in content:
            return json.dumps({"error": "Old string not found in file"})

        count = content.count(old_string)
        if count > 1 and not replace_all:
            return json.dumps({
                "error": f"Found {count} occurrences. Use replace_all=true to replace all."
            })

        new_content = content.replace(old_string, new_string)
        if new_content == content:
            return json.dumps({"error": "No changes made"})

        # Backup
        backup_path = resolved.with_suffix(resolved.suffix + f".bak.{int(time.time())}")
        file_ops.copy(resolved, backup_path)

        file_ops.write(resolved, new_content)

        return json.dumps({
            "success": True,
            "replacements": count if replace_all else 1,
            "backup": str(backup_path),
        })

    except Exception as e:
        logger.exception("edit_file error: %s", e)
        return json.dumps({"error": f"Edit failed: {e}"})


def rename_file(
    path: str,
    new_name: str,
    overwrite: bool = False,
    task_id: str = "default",
) -> str:
    """Rename a file or directory."""
    try:
        resolved = _resolve_path(path, task_id)
        file_ops = _get_file_ops_for_task(task_id)

        if not file_ops.exists(resolved):
            return json.dumps({"error": f"Source not found: {path}"})

        new_path = resolved.parent / new_name
        error = _validate_write_path(str(new_path), task_id)
        if error:
            return json.dumps({"error": error})

        if file_ops.exists(new_path) and not overwrite:
            return json.dumps({"error": f"Destination exists: {new_name}"})

        file_ops.rename(resolved, new_path)

        return json.dumps({
            "success": True,
            "old_path": str(resolved),
            "new_path": str(new_path),
        })

    except Exception as e:
        logger.exception("rename_file error: %s", e)
        return json.dumps({"error": f"Rename failed: {e}"})


def move_file(
    source: str,
    destination: str,
    overwrite: bool = False,
    task_id: str = "default",
) -> str:
    """Move a file or directory."""
    try:
        src_resolved = _resolve_path(source, task_id)
        dst_resolved = _resolve_path(destination, task_id)
        file_ops = _get_file_ops_for_task(task_id)

        if not file_ops.exists(src_resolved):
            return json.dumps({"error": f"Source not found: {source}"})

        error = _validate_write_path(str(dst_resolved), task_id)
        if error:
            return json.dumps({"error": error})

        if file_ops.exists(dst_resolved) and not overwrite:
            return json.dumps({"error": f"Destination exists: {destination}"})

        # Ensure parent exists
        if not file_ops.exists(dst_resolved.parent):
            file_ops.makedirs(dst_resolved.parent, exist_ok=True)

        file_ops.rename(src_resolved, dst_resolved)

        return json.dumps({
            "success": True,
            "source": str(src_resolved),
            "destination": str(dst_resolved),
        })

    except Exception as e:
        logger.exception("move_file error: %s", e)
        return json.dumps({"error": f"Move failed: {e}"})


def copy_file(
    source: str,
    destination: str,
    overwrite: bool = False,
    preserve_metadata: bool = True,
    task_id: str = "default",
) -> str:
    """Copy a file or directory."""
    try:
        src_resolved = _resolve_path(source, task_id)
        dst_resolved = _resolve_path(destination, task_id)
        file_ops = _get_file_ops_for_task(task_id)

        if not file_ops.exists(src_resolved):
            return json.dumps({"error": f"Source not found: {source}"})

        error = _validate_write_path(str(dst_resolved), task_id)
        if error:
            return json.dumps({"error": error})

        if file_ops.exists(dst_resolved) and not overwrite:
            return json.dumps({"error": f"Destination exists: {destination}"})

        if not file_ops.exists(dst_resolved.parent):
            file_ops.makedirs(dst_resolved.parent, exist_ok=True)

        if file_ops.is_dir(src_resolved):
            file_ops.copytree(src_resolved, dst_resolved, dirs_exist_ok=overwrite)
        else:
            file_ops.copy2(src_resolved, dst_resolved) if preserve_metadata else file_ops.copy(src_resolved, dst_resolved)

        return json.dumps({
            "success": True,
            "source": str(src_resolved),
            "destination": str(dst_resolved),
        })

    except Exception as e:
        logger.exception("copy_file error: %s", e)
        return json.dumps({"error": f"Copy failed: {e}"})


def delete_file(
    path: str,
    recursive: bool = False,
    trash: bool = True,
    task_id: str = "default",
) -> str:
    """Delete a file or directory."""
    try:
        resolved = _resolve_path(path, task_id)
        file_ops = _get_file_ops_for_task(task_id)

        if not file_ops.exists(resolved):
            return json.dumps({"error": f"Path not found: {path}"})

        error = _validate_write_path(path, task_id)
        if error:
            return json.dumps({"error": error})

        if file_ops.is_dir(resolved) and not recursive:
            return json.dumps({"error": "Directory not empty. Use recursive=true."})

        if trash:
            # Move to trash
            trash_dir = Path.home() / ".local" / "share" / "Trash" / "files"
            trash_dir.mkdir(parents=True, exist_ok=True)
            trash_path = trash_dir / f"{resolved.name}.{int(time.time())}"
            file_ops.rename(resolved, trash_path)
            return json.dumps({
                "success": True,
                "message": f"Moved to trash: {trash_path}",
            })
        else:
            if file_ops.is_dir(resolved):
                file_ops.rmtree(resolved)
            else:
                file_ops.remove(resolved)
            return json.dumps({"success": True, "message": "Deleted permanently"})

    except Exception as e:
        logger.exception("delete_file error: %s", e)
        return json.dumps({"error": f"Delete failed: {e}"})


def search_files_advanced(
    pattern: str,
    path: str = ".",
    recursive: bool = True,
    file_type: Optional[str] = None,  # file, dir, symlink
    regex: bool = False,
    content_pattern: Optional[str] = None,
    content_regex: bool = False,
    max_results: int = 100,
    offset: int = 0,
    task_id: str = "default",
) -> str:
    """Advanced file search with multiple filters."""
    try:
        resolved = _resolve_path(path, task_id)
        file_ops = _get_file_ops_for_task(task_id)

        if not file_ops.exists(resolved):
            return json.dumps({"error": f"Path not found: {path}"})

        import fnmatch
        import re

        pattern_re = re.compile(pattern) if regex else None
        content_re = re.compile(content_pattern) if content_regex and content_pattern else None
        content_fn = fnmatch.translate(content_pattern) if content_pattern and not content_regex else None
        if content_fn:
            content_re = re.compile(content_fn)

        matches = []
        count = 0

        def check_file(p: Path):
            nonlocal count
            if count >= max_results:
                return

            rel = p.relative_to(resolved)
            name = str(rel)

            # Check name pattern
            if pattern_re:
                if not pattern_re.search(name):
                    return
            elif not fnmatch.fnmatch(name, pattern):
                return

            # Check file type
            if file_type:
                if file_type == "file" and not file_ops.is_file(p):
                    return
                elif file_type == "dir" and not file_ops.is_dir(p):
                    return
                elif file_type == "symlink" and not file_ops.is_symlink(p):
                    return

            # Check content
            if content_re and file_ops.is_file(p) and not has_binary_extension(str(p)):
                try:
                    text = file_ops.read(p)
                    if not content_re.search(text):
                        return
                except Exception:
                    return

            if count >= offset:
                stat = file_ops.stat(p)
                matches.append({
                    "path": str(rel),
                    "absolute_path": str(p),
                    "size": stat.st_size,
                    "modified": stat.st_mtime,
                    "is_dir": file_ops.is_dir(p),
                })
            count += 1

        if recursive:
            for root, dirs, files in file_ops.walk(resolved):
                for f in files + dirs:
                    check_file(Path(root) / f)
                    if count >= max_results + offset:
                        break
        else:
            for f in file_ops.listdir(resolved):
                check_file(f)
                if count >= max_results + offset:
                    break

        return json.dumps({
            "matches": matches,
            "total": count,
            "offset": offset,
            "limit": max_results,
        })

    except Exception as e:
        logger.exception("search_files_advanced error: %s", e)
        return json.dumps({"error": f"Search failed: {e}"})


def watch_files(
    path: str,
    watch_id: str,
    action: str = "start",  # start, stop, get_events
    recursive: bool = True,
    task_id: str = "default",
) -> str:
    """Watch files for changes."""
    try:
        if action == "start":
            resolved = _resolve_path(path, task_id)
            file_ops = _get_file_ops_for_task(task_id)

            if not file_ops.exists(resolved):
                return json.dumps({"error": f"Path not found: {path}"})

            if not file_ops.is_dir(resolved):
                return json.dumps({"error": "Watch path must be a directory"})

            # Check if already watching
            existing = _get_watcher(task_id, watch_id)
            if existing:
                return json.dumps({"error": f"Watch {watch_id} already exists"})

            # Create watcher
            observer = Observer()
            handler = FileWatchHandler(task_id, watch_id)
            observer.schedule(handler, str(resolved), recursive=recursive)
            observer.start()

            _register_watcher(task_id, watch_id, observer)

            # Initialize event buffer
            with _watch_events_lock:
                _watch_events[watch_id] = []

            return json.dumps({
                "success": True,
                "watch_id": watch_id,
                "path": str(resolved),
                "recursive": recursive,
            })

        elif action == "stop":
            observer = _get_watcher(task_id, watch_id)
            if not observer:
                return json.dumps({"error": f"Watch {watch_id} not found"})

            observer.stop()
            observer.join(timeout=5)
            _unregister_watcher(task_id, watch_id)

            with _watch_events_lock:
                events = _watch_events.pop(watch_id, [])

            return json.dumps({
                "success": True,
                "watch_id": watch_id,
                "events_captured": len(events),
            })

        elif action == "get_events":
            with _watch_events_lock:
                events = _watch_events.get(watch_id, []).copy()

            return json.dumps({
                "watch_id": watch_id,
                "events": events,
                "count": len(events),
            })

        else:
            return json.dumps({"error": f"Invalid action: {action}"})

    except Exception as e:
        logger.exception("watch_files error: %s", e)
        return json.dumps({"error": f"Watch failed: {e}"})


def handle_binary_file(
    path: str,
    action: str,  # read, write, encode, decode
    content: Optional[str] = None,  # base64 for write/encode
    encoding: str = "base64",  # base64, hex
    task_id: str = "default",
) -> str:
    """Handle binary files with encoding/decoding."""
    try:
        resolved = _resolve_path(path, task_id)
        file_ops = _get_file_ops_for_task(task_id)

        if action == "read":
            if not file_ops.exists(resolved):
                return json.dumps({"error": f"File not found: {path}"})

            data = file_ops.read_bytes(resolved)
            if encoding == "base64":
                import base64
                encoded = base64.b64encode(data).decode('ascii')
            elif encoding == "hex":
                encoded = data.hex()
            else:
                return json.dumps({"error": f"Unsupported encoding: {encoding}"})

            return json.dumps({
                "content": encoded,
                "encoding": encoding,
                "size": len(data),
            })

        elif action == "write":
            if content is None:
                return json.dumps({"error": "Content required for write"})

            error = _validate_write_path(path, task_id)
            if error:
                return json.dumps({"error": error})

            if encoding == "base64":
                import base64
                data = base64.b64decode(content)
            elif encoding == "hex":
                data = bytes.fromhex(content)
            else:
                return json.dumps({"error": f"Unsupported encoding: {encoding}"})

            if not file_ops.exists(resolved.parent):
                file_ops.makedirs(resolved.parent, exist_ok=True)

            file_ops.write_bytes(resolved, data)
            return json.dumps({"success": True, "size": len(data)})

        elif action == "encode":
            if not file_ops.exists(resolved):
                return json.dumps({"error": f"File not found: {path}"})

            data = file_ops.read_bytes(resolved)
            if encoding == "base64":
                import base64
                encoded = base64.b64encode(data).decode('ascii')
            elif encoding == "hex":
                encoded = data.hex()
            else:
                return json.dumps({"error": f"Unsupported encoding: {encoding}"})

            return json.dumps({"content": encoded, "encoding": encoding})

        elif action == "decode":
            if content is None:
                return json.dumps({"error": "Content required for decode"})

            if encoding == "base64":
                import base64
                data = base64.b64decode(content)
            elif encoding == "hex":
                data = bytes.fromhex(content)
            else:
                return json.dumps({"error": f"Unsupported encoding: {encoding}"})

            return json.dumps({"content": data.decode('utf-8', errors='replace')})

        else:
            return json.dumps({"error": f"Invalid action: {action}"})

    except Exception as e:
        logger.exception("handle_binary_file error: %s", e)
        return json.dumps({"error": f"Binary file operation failed: {e}"})


def extract_archive(
    archive_path: str,
    destination: Optional[str] = None,
    overwrite: bool = False,
    task_id: str = "default",
) -> str:
    """Extract an archive file."""
    try:
        resolved = _resolve_path(archive_path, task_id)
        file_ops = _get_file_ops_for_task(task_id)

        if not file_ops.exists(resolved):
            return json.dumps({"error": f"Archive not found: {archive_path}"})

        # Determine archive type
        ext = None
        for known_ext in sorted(ARCHIVE_EXTENSIONS.keys(), key=len, reverse=True):
            if str(resolved).lower().endswith(known_ext):
                ext = ARCHIVE_EXTENSIONS[known_ext]
                break

        if not ext:
            return json.dumps({"error": f"Unsupported archive format: {archive_path}"})

        # Destination
        if destination:
            dest_path = _resolve_path(destination, task_id)
        else:
            dest_path = resolved.parent / resolved.stem

        if file_ops.exists(dest_path) and not overwrite:
            return json.dumps({"error": f"Destination exists: {dest_path}"})

        if not file_ops.exists(dest_path):
            file_ops.makedirs(dest_path, exist_ok=True)

        # Extract based on type
        extracted = []

        if ext == "zip":
            import zipfile
            with zipfile.ZipFile(resolved, 'r') as zf:
                zf.extractall(dest_path)
                extracted = zf.namelist()

        elif ext in ("tar", "tar.gz", "tar.bz2", "tar.xz"):
            import tarfile
            mode = {
                "tar": "r",
                "tar.gz": "r:gz",
                "tar.bz2": "r:bz2",
                "tar.xz": "r:xz",
            }[ext]
            with tarfile.open(resolved, mode) as tf:
                tf.extractall(dest_path)
                extracted = tf.getnames()

        elif ext == "gzip":
            import gzip
            import shutil
            out_path = dest_path / resolved.stem
            with gzip.open(resolved, 'rb') as f_in:
                with open(out_path, 'wb') as f_out:
                    shutil.copyfileobj(f_in, f_out)
            extracted = [out_path.name]

        elif ext == "bzip2":
            import bz2
            import shutil
            out_path = dest_path / resolved.stem
            with bz2.open(resolved, 'rb') as f_in:
                with open(out_path, 'wb') as f_out:
                    shutil.copyfileobj(f_in, f_out)
            extracted = [out_path.name]

        elif ext == "xz":
            import lzma
            import shutil
            out_path = dest_path / resolved.stem
            with lzma.open(resolved, 'rb') as f_in:
                with open(out_path, 'wb') as f_out:
                    shutil.copyfileobj(f_in, f_out)
            extracted = [out_path.name]

        elif ext in ("7z", "rar"):
            # Requires external tools
            cmd = ["7z", "x", str(resolved), f"-o{dest_path}", "-y"] if ext == "7z" else ["unrar", "x", str(resolved), str(dest_path)]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            if result.returncode != 0:
                return json.dumps({"error": f"Extraction failed: {result.stderr}"})
            extracted = ["extracted via external tool"]

        else:
            return json.dumps({"error": f"Unsupported archive type: {ext}"})

        return json.dumps({
            "success": True,
            "archive": str(resolved),
            "destination": str(dest_path),
            "extracted_count": len(extracted),
            "files": extracted[:100],  # Limit output
        })

    except Exception as e:
        logger.exception("extract_archive error: %s", e)
        return json.dumps({"error": f"Extraction failed: {e}"})


def create_archive(
    source_paths: List[str],
    archive_path: str,
    format: str = "zip",  # zip, tar, tar.gz, tar.bz2, tar.xz, 7z
    compression_level: int = 6,
    task_id: str = "default",
) -> str:
    """Create an archive from files/directories."""
    try:
        archive_resolved = _resolve_path(archive_path, task_id)
        file_ops = _get_file_ops_for_task(task_id)

        error = _validate_write_path(archive_path, task_id)
        if error:
            return json.dumps({"error": error})

        # Resolve source paths
        sources = [_resolve_path(p, task_id) for p in source_paths]
        for s in sources:
            if not file_ops.exists(s):
                return json.dumps({"error": f"Source not found: {s}"})

        if not file_ops.exists(archive_resolved.parent):
            file_ops.makedirs(archive_resolved.parent, exist_ok=True)

        if format == "zip":
            import zipfile
            with zipfile.ZipFile(archive_resolved, 'w', zipfile.ZIP_DEFLATED, compresslevel=compression_level) as zf:
                for src in sources:
                    if file_ops.is_dir(src):
                        for root, dirs, files in file_ops.walk(src):
                            for f in files:
                                full = Path(root) / f
                                arc = full.relative_to(src.parent)
                                zf.write(full, arc)
                    else:
                        zf.write(src, src.name)

        elif format in ("tar", "tar.gz", "tar.bz2", "tar.xz"):
            import tarfile
            mode = {
                "tar": "w",
                "tar.gz": "w:gz",
                "tar.bz2": "w:bz2",
                "tar.xz": "w:xz",
            }[format]
            with tarfile.open(archive_resolved, mode) as tf:
                for src in sources:
                    tf.add(src, arcname=src.name)

        elif format == "7z":
            cmd = ["7z", "a", f"-mx={compression_level}", str(archive_resolved)] + [str(s) for s in sources]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            if result.returncode != 0:
                return json.dumps({"error": f"Archive creation failed: {result.stderr}"})

        else:
            return json.dumps({"error": f"Unsupported format: {format}"})

        stat = file_ops.stat(archive_resolved)
        return json.dumps({
            "success": True,
            "archive": str(archive_resolved),
            "format": format,
            "size": stat.st_size,
            "sources": source_paths,
        })

    except Exception as e:
        logger.exception("create_archive error: %s", e)
        return json.dumps({"error": f"Archive creation failed: {e}"})


def generate_checksum(
    path: str,
    algorithm: str = "sha256",  # md5, sha1, sha256, sha512, blake3
    task_id: str = "default",
) -> str:
    """Generate file checksum."""
    try:
        resolved = _resolve_path(path, task_id)
        file_ops = _get_file_ops_for_task(task_id)

        if not file_ops.exists(resolved):
            return json.dumps({"error": f"File not found: {path}"})

        if file_ops.is_dir(resolved):
            return json.dumps({"error": "Cannot checksum directory"})

        algo = CHECKSUM_ALGORITHMS.get(algorithm.lower())
        if not algo:
            return json.dumps({"error": f"Unsupported algorithm: {algorithm}"})

        # Stream hash for large files
        hasher = algo()
        chunk_size = 8192

        with file_ops.open(resolved, 'rb') as f:
            while chunk := f.read(chunk_size):
                hasher.update(chunk)

        checksum = hasher.hexdigest()
        return json.dumps({
            "path": str(resolved),
            "algorithm": algorithm,
            "checksum": checksum,
        })

    except Exception as e:
        logger.exception("generate_checksum error: %s", e)
        return json.dumps({"error": f"Checksum failed: {e}"})


def index_workspace(
    path: str = ".",
    include_patterns: Optional[List[str]] = None,
    exclude_patterns: Optional[List[str]] = None,
    max_files: int = 10000,
    task_id: str = "default",
) -> str:
    """Build a searchable workspace index."""
    try:
        resolved = _resolve_path(path, task_id)
        file_ops = _get_file_ops_for_task(task_id)

        if not file_ops.exists(resolved):
            return json.dumps({"error": f"Path not found: {path}"})

        import fnmatch

        include_patterns = include_patterns or ["*"]
        exclude_patterns = exclude_patterns or [
            "*.pyc", "__pycache__", ".git", "node_modules",
            ".venv", "venv", "*.log", "*.tmp", ".DS_Store",
        ]

        def should_index(p: Path) -> bool:
            name = p.name
            rel = str(p.relative_to(resolved))

            # Check excludes
            for pat in exclude_patterns:
                if fnmatch.fnmatch(name, pat) or fnmatch.fnmatch(rel, pat):
                    return False

            # Check includes
            for pat in include_patterns:
                if fnmatch.fnmatch(name, pat) or fnmatch.fnmatch(rel, pat):
                    return True
            return False

        index = {
            "files": [],
            "directories": [],
            "total_size": 0,
            "file_count": 0,
            "dir_count": 0,
        }

        count = 0
        for root, dirs, files in file_ops.walk(resolved):
            root_path = Path(root)

            # Index directories
            for d in dirs:
                d_path = root_path / d
                if should_index(d_path):
                    stat = file_ops.stat(d_path)
                    index["directories"].append({
                        "path": str(d_path.relative_to(resolved)),
                        "modified": stat.st_mtime,
                    })
                    index["dir_count"] += 1

            # Index files
            for f in files:
                if count >= max_files:
                    break
                f_path = root_path / f
                if should_index(f_path):
                    stat = file_ops.stat(f_path)
                    index["files"].append({
                        "path": str(f_path.relative_to(resolved)),
                        "size": stat.st_size,
                        "modified": stat.st_mtime,
                        "extension": f_path.suffix.lower(),
                    })
                    index["total_size"] += stat.st_size
                    index["file_count"] += 1
                    count += 1

            if count >= max_files:
                break

        return json.dumps(index, default=str)

    except Exception as e:
        logger.exception("index_workspace error: %s", e)
        return json.dumps({"error": f"Indexing failed: {e}"})


# Register all tools
def _register_filesystem_tools():
    """Register all filesystem tools with the registry."""

    tools = [
        ("read_file_advanced", "filesystem_advanced", {
            "name": "read_file_advanced",
            "description": "Read a file with advanced options (encoding, binary, pagination)",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File path"},
                    "offset": {"type": "integer", "description": "Line offset (1-indexed)", "default": 1},
                    "limit": {"type": "integer", "description": "Max lines to read", "default": 500},
                    "encoding": {"type": "string", "description": "Text encoding", "default": "utf-8"},
                    "binary": {"type": "boolean", "description": "Read as binary (base64)", "default": False},
                },
                "required": ["path"],
            },
        }, read_file_advanced, None, [], False, "📖", None),

        ("write_file_advanced", "filesystem_advanced", {
            "name": "write_file_advanced",
            "description": "Write a file with advanced options (backup, atomic, permissions)",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File path"},
                    "content": {"type": "string", "description": "File content (or base64 if binary)"},
                    "encoding": {"type": "string", "description": "Text encoding", "default": "utf-8"},
                    "binary": {"type": "boolean", "description": "Content is base64 encoded", "default": False},
                    "backup": {"type": "boolean", "description": "Create backup of existing file", "default": True},
                    "atomic": {"type": "boolean", "description": "Atomic write via temp file", "default": True},
                    "permissions": {"type": "string", "description": "File permissions (octal)", "default": None},
                    "create_dirs": {"type": "boolean", "description": "Create parent directories", "default": True},
                },
                "required": ["path", "content"],
            },
        }, write_file_advanced, None, [], False, "📝", None),

        ("edit_file", "filesystem_advanced", {
            "name": "edit_file",
            "description": "Edit a file by replacing text",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File path"},
                    "old_string": {"type": "string", "description": "Text to replace"},
                    "new_string": {"type": "string", "description": "Replacement text"},
                    "replace_all": {"type": "boolean", "description": "Replace all occurrences", "default": False},
                },
                "required": ["path", "old_string", "new_string"],
            },
        }, edit_file, None, [], False, "✏️", None),

        ("rename_file", "filesystem_advanced", {
            "name": "rename_file",
            "description": "Rename a file or directory",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Current path"},
                    "new_name": {"type": "string", "description": "New name"},
                    "overwrite": {"type": "boolean", "description": "Overwrite if exists", "default": False},
                },
                "required": ["path", "new_name"],
            },
        }, rename_file, None, [], False, "📛", None),

        ("move_file", "filesystem_advanced", {
            "name": "move_file",
            "description": "Move a file or directory",
            "parameters": {
                "type": "object",
                "properties": {
                    "source": {"type": "string", "description": "Source path"},
                    "destination": {"type": "string", "description": "Destination path"},
                    "overwrite": {"type": "boolean", "description": "Overwrite if exists", "default": False},
                },
                "required": ["source", "destination"],
            },
        }, move_file, None, [], False, "📦", None),

        ("copy_file", "filesystem_advanced", {
            "name": "copy_file",
            "description": "Copy a file or directory",
            "parameters": {
                "type": "object",
                "properties": {
                    "source": {"type": "string", "description": "Source path"},
                    "destination": {"type": "string", "description": "Destination path"},
                    "overwrite": {"type": "boolean", "description": "Overwrite if exists", "default": False},
                    "preserve_metadata": {"type": "boolean", "description": "Preserve timestamps/permissions", "default": True},
                },
                "required": ["source", "destination"],
            },
        }, copy_file, None, [], False, "📋", None),

        ("delete_file", "filesystem_advanced", {
            "name": "delete_file",
            "description": "Delete a file or directory (with trash support)",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Path to delete"},
                    "recursive": {"type": "boolean", "description": "Delete directories recursively", "default": False},
                    "trash": {"type": "boolean", "description": "Move to trash instead of permanent delete", "default": True},
                },
                "required": ["path"],
            },
        }, delete_file, None, [], False, "🗑️", None),

        ("search_files_advanced", "filesystem_advanced", {
            "name": "search_files_advanced",
            "description": "Advanced file search with multiple filters",
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {"type": "string", "description": "File name pattern (glob or regex)"},
                    "path": {"type": "string", "description": "Search root path", "default": "."},
                    "recursive": {"type": "boolean", "description": "Search recursively", "default": True},
                    "file_type": {"type": "string", "enum": ["file", "dir", "symlink"], "description": "Filter by type"},
                    "regex": {"type": "boolean", "description": "Pattern is regex", "default": False},
                    "content_pattern": {"type": "string", "description": "Content pattern to search"},
                    "content_regex": {"type": "boolean", "description": "Content pattern is regex", "default": False},
                    "max_results": {"type": "integer", "description": "Max results", "default": 100},
                    "offset": {"type": "integer", "description": "Result offset", "default": 0},
                },
                "required": ["pattern"],
            },
        }, search_files_advanced, None, [], False, "🔍", None),

        ("watch_files", "filesystem_advanced", {
            "name": "watch_files",
            "description": "Watch files for changes",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Directory to watch"},
                    "watch_id": {"type": "string", "description": "Unique watch identifier"},
                    "action": {"type": "string", "enum": ["start", "stop", "get_events"], "default": "start"},
                    "recursive": {"type": "boolean", "description": "Watch recursively", "default": True},
                },
                "required": ["path", "watch_id"],
            },
        }, watch_files, None, [], False, "👁️", None),

        ("handle_binary_file", "filesystem_advanced", {
            "name": "handle_binary_file",
            "description": "Handle binary files with encoding/decoding",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File path"},
                    "action": {"type": "string", "enum": ["read", "write", "encode", "decode"]},
                    "content": {"type": "string", "description": "Base64/hex content for write/encode"},
                    "encoding": {"type": "string", "enum": ["base64", "hex"], "default": "base64"},
                },
                "required": ["path", "action"],
            },
        }, handle_binary_file, None, [], False, "🔢", None),

        ("extract_archive", "filesystem_advanced", {
            "name": "extract_archive",
            "description": "Extract archive files (zip, tar, gz, bz2, xz, 7z, rar)",
            "parameters": {
                "type": "object",
                "properties": {
                    "archive_path": {"type": "string", "description": "Archive file path"},
                    "destination": {"type": "string", "description": "Extract destination", "default": None},
                    "overwrite": {"type": "boolean", "description": "Overwrite existing", "default": False},
                },
                "required": ["archive_path"],
            },
        }, extract_archive, None, [], False, "📂", None),

        ("create_archive", "filesystem_advanced", {
            "name": "create_archive",
            "description": "Create archive from files/directories",
            "parameters": {
                "type": "object",
                "properties": {
                    "source_paths": {"type": "array", "items": {"type": "string"}, "description": "Paths to archive"},
                    "archive_path": {"type": "string", "description": "Output archive path"},
                    "format": {"type": "string", "enum": ["zip", "tar", "tar.gz", "tar.bz2", "tar.xz", "7z"], "default": "zip"},
                    "compression_level": {"type": "integer", "description": "Compression level (1-9)", "default": 6},
                },
                "required": ["source_paths", "archive_path"],
            },
        }, create_archive, None, [], False, "📦", None),

        ("generate_checksum", "filesystem_advanced", {
            "name": "generate_checksum",
            "description": "Generate file checksum (md5, sha1, sha256, sha512, blake3)",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File path"},
                    "algorithm": {"type": "string", "enum": ["md5", "sha1", "sha256", "sha512", "blake3"], "default": "sha256"},
                },
                "required": ["path"],
            },
        }, generate_checksum, None, [], False, "🔐", None),

        ("index_workspace", "filesystem_advanced", {
            "name": "index_workspace",
            "description": "Build searchable workspace index",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Workspace root", "default": "."},
                    "include_patterns": {"type": "array", "items": {"type": "string"}, "description": "Include patterns"},
                    "exclude_patterns": {"type": "array", "items": {"type": "string"}, "description": "Exclude patterns"},
                    "max_files": {"type": "integer", "description": "Max files to index", "default": 10000},
                },
                "required": [],
            },
        }, index_workspace, None, [], False, "📇", None),
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
_register_filesystem_tools()

# Export for external use
__all__ = [
    "read_file_advanced",
    "write_file_advanced",
    "edit_file",
    "rename_file",
    "move_file",
    "copy_file",
    "delete_file",
    "search_files_advanced",
    "watch_files",
    "handle_binary_file",
    "extract_archive",
    "create_archive",
    "generate_checksum",
    "index_workspace",
]

if __name__ == "__main__":
    # Quick test
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        test_file = Path(tmp) / "test.txt"
        test_file.write_text("Hello\nWorld\nTest")
        print("Filesystem tools loaded successfully")