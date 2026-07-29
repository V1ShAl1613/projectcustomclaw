#!/usr/bin/env python3
"""
Database Tools Module

Provides database operations for multiple database types:
- PostgreSQL, MySQL, SQLite, MongoDB, Redis
- Query execution, schema visualization
- Migration execution, backup/restore

All operations respect workspace boundaries and use existing Hermes
credential management and terminal environments.
"""

import json
import logging
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

from tools.registry import registry
from tools.file_tools import _resolve_path_for_task, _get_file_ops
from tools.terminal_tool import terminal_tool

logger = logging.getLogger(__name__)

# Supported databases
DATABASE_TYPES = {
    "postgresql": {
        "cli": "psql",
        "dump": "pg_dump",
        "restore": "psql",
        "url_prefix": "postgresql://",
    },
    "mysql": {
        "cli": "mysql",
        "dump": "mysqldump",
        "restore": "mysql",
        "url_prefix": "mysql://",
    },
    "sqlite": {
        "cli": "sqlite3",
        "dump": "sqlite3",
        "restore": "sqlite3",
        "url_prefix": "sqlite://",
    },
    "mongodb": {
        "cli": "mongosh",
        "dump": "mongodump",
        "restore": "mongorestore",
        "url_prefix": "mongodb://",
    },
    "redis": {
        "cli": "redis-cli",
        "dump": "redis-cli",
        "restore": "redis-cli",
        "url_prefix": "redis://",
    },
}


def _get_db_config(db_type: str, config: Optional[Dict] = None) -> Dict[str, Any]:
    """Get database configuration from config or environment."""
    if config:
        return config
    
    # Try environment variables
    prefix = db_type.upper()
    return {
        "host": os.getenv(f"{prefix}_HOST", "localhost"),
        "port": os.getenv(f"{prefix}_PORT", _default_port(db_type)),
        "database": os.getenv(f"{prefix}_DATABASE", os.getenv(f"{prefix}_DB", "")),
        "user": os.getenv(f"{prefix}_USER", os.getenv(f"{prefix}_USERNAME", "")),
        "password": os.getenv(f"{prefix}_PASSWORD", os.getenv(f"{prefix}_PASS", "")),
        "url": os.getenv(f"{prefix}_URL", ""),
    }


def _default_port(db_type: str) -> int:
    """Get default port for database type."""
    ports = {
        "postgresql": 5432,
        "mysql": 3306,
        "sqlite": None,
        "mongodb": 27017,
        "redis": 6379,
    }
    return ports.get(db_type)


def _build_connection_string(db_type: str, config: Dict[str, Any]) -> str:
    """Build connection string for database."""
    if config.get("url"):
        return config["url"]
    
    info = DATABASE_TYPES[db_type]
    prefix = info["url_prefix"]
    
    if db_type == "sqlite":
        db_path = config.get("database", "database.db")
        return f"{prefix}{db_path}"
    
    user = config.get("user", "")
    password = config.get("password", "")
    host = config.get("host", "localhost")
    port = config.get("port", _default_port(db_type))
    database = config.get("database", "")
    
    auth = ""
    if user:
        auth = user
        if password:
            auth += f":{password}"
        auth += "@"
    
    return f"{prefix}{auth}{host}:{port}/{database}"


def _check_db_tool_available(db_type: str, tool: str) -> bool:
    """Check if a database CLI tool is available."""
    tool_name = DATABASE_TYPES[db_type][tool]
    try:
        subprocess.run([tool_name, "--version"], capture_output=True, check=False)
        return True
    except FileNotFoundError:
        return False


def db_query(
    query: str,
    db_type: str = "postgresql",
    config: Optional[Dict] = None,
    output_format: str = "json",
    limit: int = 1000,
    task_id: str = "default",
) -> str:
    """Execute a database query.
    
    Args:
        query: SQL query to execute
        db_type: Database type (postgresql, mysql, sqlite, mongodb, redis)
        config: Database connection configuration
        output_format: Output format (json, csv, table)
        limit: Maximum rows to return
        task_id: Task identifier
        
    Returns:
        JSON string with query results
    """
    db_type = db_type.lower()
    if db_type not in DATABASE_TYPES:
        return json.dumps({"error": f"Unsupported database type: {db_type}"})
    
    db_config = _get_db_config(db_type, config)
    conn_str = _build_connection_string(db_type, db_config)
    
    try:
        if db_type == "postgresql":
            cmd = f'psql "{conn_str}" -c "{query}" --csv'
            if output_format == "json":
                cmd = f'psql "{conn_str}" -c "{query}" -t -A -F","'
        elif db_type == "mysql":
            cmd = f'mysql "{conn_str}" -e "{query}" --batch'
            if output_format == "json":
                cmd += " --raw"
        elif db_type == "sqlite":
            cmd = f'sqlite3 "{db_config.get("database", "database.db")}" "{query}"'
            if output_format == "json":
                cmd += " -json"
        elif db_type == "mongodb":
            # MongoDB uses JavaScript
            cmd = f'mongosh "{conn_str}" --eval "db.runCommand({{find: \\"collection\\", filter: {{}}}}).toArray()"'
        elif db_type == "redis":
            # Redis CLI
            cmd = f'redis-cli -u "{conn_str}" --raw {query}'
        else:
            return json.dumps({"error": f"Query not implemented for {db_type}"})
        
        result = terminal_tool(command=cmd, timeout=60, task_id=task_id)
        return result
        
    except Exception as e:
        logger.exception("Database query failed")
        return json.dumps({"error": str(e)})


def db_schema(
    db_type: str = "postgresql",
    config: Optional[Dict] = None,
    schema: Optional[str] = None,
    table: Optional[str] = None,
    output_format: str = "json",
    task_id: str = "default",
) -> str:
    """Get database schema information.
    
    Args:
        db_type: Database type
        config: Database connection configuration
        schema: Schema name (PostgreSQL)
        table: Specific table to describe
        output_format: Output format
        task_id: Task identifier
        
    Returns:
        JSON string with schema information
    """
    db_type = db_type.lower()
    if db_type not in DATABASE_TYPES:
        return json.dumps({"error": f"Unsupported database type: {db_type}"})
    
    db_config = _get_db_config(db_type, config)
    conn_str = _build_connection_string(db_type, db_config)
    
    try:
        if db_type == "postgresql":
            if table:
                query = f"""
                SELECT column_name, data_type, is_nullable, column_default
                FROM information_schema.columns
                WHERE table_name = '{table}'
                {'AND table_schema = ' + schema if schema else ''}
                ORDER BY ordinal_position;
                """
            else:
                query = """
                SELECT table_schema, table_name, column_name, data_type, is_nullable
                FROM information_schema.columns
                WHERE table_schema NOT IN ('information_schema', 'pg_catalog')
                ORDER BY table_schema, table_name, ordinal_position;
                """
            cmd = f'psql "{conn_str}" -c "{query}" --csv'
            
        elif db_type == "mysql":
            if table:
                query = f"DESCRIBE `{table}`;"
            else:
                query = "SHOW TABLES;"
            cmd = f'mysql "{conn_str}" -e "{query}" --batch'
            
        elif db_type == "sqlite":
            if table:
                query = f"PRAGMA table_info({table});"
            else:
                query = "SELECT name FROM sqlite_master WHERE type='table';"
            cmd = f'sqlite3 "{db_config.get("database", "database.db")}" "{query}" -json'
            
        elif db_type == "mongodb":
            if table:
                query = f'db.{table}.findOne()'
            else:
                query = 'db.getCollectionNames()'
            cmd = f'mongosh "{conn_str}" --eval "{query}" --quiet'
            
        elif db_type == "redis":
            cmd = f'redis-cli -u "{conn_str}" INFO'
            
        else:
            return json.dumps({"error": f"Schema not implemented for {db_type}"})
        
        result = terminal_tool(command=cmd, timeout=60, task_id=task_id)
        return result
        
    except Exception as e:
        logger.exception("Schema retrieval failed")
        return json.dumps({"error": str(e)})


def db_migrate(
    action: str = "up",
    db_type: str = "postgresql",
    config: Optional[Dict] = None,
    migration_dir: str = "migrations",
    version: Optional[str] = None,
    task_id: str = "default",
) -> str:
    """Execute database migrations.
    
    Args:
        action: Migration action (up, down, create, status)
        db_type: Database type
        config: Database connection configuration
        migration_dir: Directory containing migrations
        version: Specific version to migrate to
        task_id: Task identifier
        
    Returns:
        JSON string with migration result
    """
    db_type = db_type.lower()
    resolved_dir = _resolve_path(migration_dir, task_id)
    
    if not resolved_dir.exists():
        return json.dumps({"error": f"Migration directory not found: {migration_dir}"})
    
    db_config = _get_db_config(db_type, config)
    conn_str = _build_connection_string(db_type, db_config)
    
    try:
        # Check for migration tools
        if db_type in ("postgresql", "mysql"):
            # Try golang-migrate
            if _check_tool("migrate"):
                cmd = f'migrate -path "{resolved_dir}" -database "{conn_str}" {action}'
                if version:
                    cmd += f" {version}"
                result = terminal_tool(command=cmd, timeout=120, task_id=task_id)
                return result
            
            # Try dbmate
            if _check_tool("dbmate"):
                env = f'DATABASE_URL="{conn_str}"'
                cmd = f'{env} dbmate --migrations-dir "{resolved_dir}" {action}'
                if version:
                    cmd += f" --version {version}"
                result = terminal_tool(command=cmd, timeout=120, task_id=task_id)
                return result
        
        elif db_type == "sqlite":
            # Simple file-based migrations
            if action == "up":
                for migration_file in sorted(resolved_dir.glob("*.sql")):
                    cmd = f'sqlite3 "{db_config.get("database", "database.db")}" < "{migration_file}"'
                    result = terminal_tool(command=cmd, timeout=60, task_id=task_id)
                    if "error" in json.loads(result):
                        return result
                return json.dumps({"success": True, "message": "Migrations applied"})
        
        return json.dumps({"error": f"No migration tool found for {db_type}. Install migrate or dbmate"})
        
    except Exception as e:
        logger.exception("Migration failed")
        return json.dumps({"error": str(e)})


def db_backup(
    db_type: str = "postgresql",
    config: Optional[Dict] = None,
    output: Optional[str] = None,
    compress: bool = True,
    task_id: str = "default",
) -> str:
    """Backup database.
    
    Args:
        db_type: Database type
        config: Database connection configuration
        output: Output file path
        compress: Compress backup
        task_id: Task identifier
        
    Returns:
        JSON string with backup result
    """
    db_type = db_type.lower()
    if db_type not in DATABASE_TYPES:
        return json.dumps({"error": f"Unsupported database type: {db_type}"})
    
    db_config = _get_db_config(db_type, config)
    conn_str = _build_connection_string(db_type, db_config)
    
    if not output:
        timestamp = __import__("datetime").datetime.now().strftime("%Y%m%d_%H%M%S")
        ext = ".sql" if db_type in ("postgresql", "mysql", "sqlite") else ".archive"
        if compress:
            ext += ".gz"
        output = f"backup_{db_type}_{timestamp}{ext}"
    
    output_path = _resolve_path(output, task_id)
    
    try:
        if db_type == "postgresql":
            cmd = f'pg_dump "{conn_str}"'
            if compress:
                cmd += " | gzip"
            cmd += f' > "{output_path}"'
            
        elif db_type == "mysql":
            cmd = f'mysqldump "{conn_str}"'
            if compress:
                cmd += " | gzip"
            cmd += f' > "{output_path}"'
            
        elif db_type == "sqlite":
            cmd = f'sqlite3 "{db_config.get("database", "database.db")}" .dump'
            if compress:
                cmd += " | gzip"
            cmd += f' > "{output_path}"'
            
        elif db_type == "mongodb":
            cmd = f'mongodump --uri="{conn_str}" --archive="{output_path}"'
            if compress:
                cmd += " --gzip"
                
        elif db_type == "redis":
            cmd = f'redis-cli -u "{conn_str}" --rdb "{output_path}"'
            
        else:
            return json.dumps({"error": f"Backup not implemented for {db_type}"})
        
        result = terminal_tool(command=cmd, timeout=300, task_id=task_id)
        return json.dumps({
            "success": True,
            "output": str(output_path),
            "compressed": compress,
        })
        
    except Exception as e:
        logger.exception("Backup failed")
        return json.dumps({"error": str(e)})


def db_restore(
    db_type: str = "postgresql",
    config: Optional[Dict] = None,
    input_file: str = "",
    task_id: str = "default",
) -> str:
    """Restore database from backup.
    
    Args:
        db_type: Database type
        config: Database connection configuration
        input_file: Backup file to restore from
        task_id: Task identifier
        
    Returns:
        JSON string with restore result
    """
    if not input_file:
        return json.dumps({"error": "input_file required"})
    
    db_type = db_type.lower()
    if db_type not in DATABASE_TYPES:
        return json.dumps({"error": f"Unsupported database type: {db_type}"})
    
    db_config = _get_db_config(db_type, config)
    conn_str = _build_connection_string(db_type, db_config)
    
    input_path = _resolve_path(input_file, task_id)
    if not input_path.exists():
        return json.dumps({"error": f"Backup file not found: {input_file}"})
    
    try:
        is_gzipped = str(input_path).endswith(".gz")
        
        if db_type == "postgresql":
            if is_gzipped:
                cmd = f'gunzip -c "{input_path}" | psql "{conn_str}"'
            else:
                cmd = f'psql "{conn_str}" < "{input_path}"'
                
        elif db_type == "mysql":
            if is_gzipped:
                cmd = f'gunzip -c "{input_path}" | mysql "{conn_str}"'
            else:
                cmd = f'mysql "{conn_str}" < "{input_path}"'
                
        elif db_type == "sqlite":
            if is_gzipped:
                cmd = f'gunzip -c "{input_path}" | sqlite3 "{db_config.get("database", "database.db")}"'
            else:
                cmd = f'sqlite3 "{db_config.get("database", "database.db")}" < "{input_path}"'
                
        elif db_type == "mongodb":
            cmd = f'mongorestore --uri="{conn_str}" --archive="{input_path}"'
            if is_gzipped:
                cmd += " --gzip"
                
        elif db_type == "redis":
            # Redis restore is more complex - need to stop server, replace rdb, restart
            return json.dumps({"error": "Redis restore requires manual intervention"})
            
        else:
            return json.dumps({"error": f"Restore not implemented for {db_type}"})
        
        result = terminal_tool(command=cmd, timeout=300, task_id=task_id)
        return json.dumps({"success": True, "message": "Database restored"})
        
    except Exception as e:
        logger.exception("Restore failed")
        return json.dumps({"error": str(e)})


def db_list_databases(
    db_type: str = "postgresql",
    config: Optional[Dict] = None,
    task_id: str = "default",
) -> str:
    """List databases on server."""
    db_type = db_type.lower()
    db_config = _get_db_config(db_type, config)
    conn_str = _build_connection_string(db_type, db_config)
    
    try:
        if db_type == "postgresql":
            cmd = f'psql "{conn_str}" -c "SELECT datname FROM pg_database WHERE datistemplate = false;" --csv'
        elif db_type == "mysql":
            cmd = f'mysql "{conn_str}" -e "SHOW DATABASES;" --batch'
        elif db_type == "mongodb":
            cmd = f'mongosh "{conn_str}" --eval "db.adminCommand({{listDatabases: 1}})" --quiet'
        elif db_type == "redis":
            cmd = f'redis-cli -u "{conn_str}" INFO keyspace'
        else:
            return json.dumps({"error": f"Not implemented for {db_type}"})
        
        result = terminal_tool(command=cmd, timeout=30, task_id=task_id)
        return result
    except Exception as e:
        return json.dumps({"error": str(e)})


def db_explain(
    query: str,
    db_type: str = "postgresql",
    config: Optional[Dict] = None,
    analyze: bool = False,
    task_id: str = "default",
) -> str:
    """Explain query execution plan."""
    db_type = db_type.lower()
    db_config = _get_db_config(db_type, config)
    conn_str = _build_connection_string(db_type, db_config)
    
    try:
        if db_type == "postgresql":
            analyze_str = "ANALYZE, " if analyze else ""
            cmd = f'psql "{conn_str}" -c "EXPLAIN ({analyze_str}FORMAT JSON) {query}" --csv'
        elif db_type == "mysql":
            cmd = f'mysql "{conn_str}" -e "EXPLAIN FORMAT=JSON {query}" --batch'
        elif db_type == "sqlite":
            cmd = f'sqlite3 "{db_config.get("database", "database.db")}" "EXPLAIN QUERY PLAN {query}"'
        else:
            return json.dumps({"error": f"EXPLAIN not implemented for {db_type}"})
        
        result = terminal_tool(command=cmd, timeout=60, task_id=task_id)
        return result
    except Exception as e:
        return json.dumps({"error": str(e)})


def _check_tool(name: str) -> bool:
    """Check if a command-line tool is available."""
    try:
        subprocess.run([name, "--version"], capture_output=True, check=False)
        return True
    except FileNotFoundError:
        return False


def _register_database_tools():
    """Register all database tools with the registry."""
    tools = [
        ("db_query", db_query, "Execute database query"),
        ("db_schema", db_schema, "Get database schema information"),
        ("db_migrate", db_migrate, "Execute database migrations"),
        ("db_backup", db_backup, "Backup database"),
        ("db_restore", db_restore, "Restore database from backup"),
        ("db_list_databases", db_list_databases, "List databases on server"),
        ("db_explain", db_explain, "Explain query execution plan"),
    ]
    
    for name, func, desc in tools:
        registry.register(
            name=name,
            toolset="database",
            schema={"name": name, "description": desc, "parameters": {"type": "object", "properties": {}}},
            handler=func,
            check_fn=lambda: True,
            description=desc,
        )


_register_database_tools()