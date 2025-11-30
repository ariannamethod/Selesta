#!/usr/bin/env python3
"""
Resonance Database Rotation Manager
Auto-backup when database exceeds size limit
"""

import os
import shutil
import sqlite3
from pathlib import Path
from datetime import datetime

# Configuration
MAX_SIZE_MB = 200
DB_NAME = "resonance.sqlite3"
BACKUP_DIR = ".resonance_backups"


def get_db_size_mb(db_path: Path) -> float:
    """Get database size in MB"""
    if not db_path.exists():
        return 0.0
    
    size_bytes = db_path.stat().st_size
    return size_bytes / (1024 * 1024)


def create_backup(db_path: Path, backup_dir: Path) -> Path:
    """Create timestamped backup of database"""
    backup_dir.mkdir(parents=True, exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    size_mb = get_db_size_mb(db_path)
    
    backup_name = f"resonance_{timestamp}_{int(size_mb)}MB.sqlite3"
    backup_path = backup_dir / backup_name
    
    shutil.copy2(db_path, backup_path)
    
    return backup_path


def vacuum_database(db_path: Path) -> None:
    """Optimize database (VACUUM)"""
    try:
        conn = sqlite3.connect(str(db_path))
        conn.execute("VACUUM")
        conn.close()
    except Exception as e:
        print(f"⚠️ VACUUM failed: {e}")


def init_fresh_database(db_path: Path, schema_file: Path = None) -> None:
    """Initialize fresh database with schema"""
    if schema_file is None:
        schema_file = db_path.parent / "init_resonance.sql"
    
    if not schema_file.exists():
        raise FileNotFoundError(f"Schema file not found: {schema_file}")
    
    # Remove old db
    if db_path.exists():
        db_path.unlink()
    
    # Create new from schema
    with open(schema_file, 'r') as f:
        schema = f.read()
    
    conn = sqlite3.connect(str(db_path))
    conn.executescript(schema)
    conn.commit()
    conn.close()


def check_and_rotate(
    db_path: Path = None,
    max_size_mb: int = MAX_SIZE_MB,
    backup_dir: Path = None
) -> dict:
    """
    Check database size and rotate if needed.
    
    Returns:
        dict with status: 'ok' | 'rotated' | 'error'
    """
    if db_path is None:
        # Auto-detect repo root
        repo_root = Path(__file__).parent.parent
        db_path = repo_root / DB_NAME
    
    if backup_dir is None:
        backup_dir = db_path.parent / BACKUP_DIR
    
    result = {
        'status': 'ok',
        'size_mb': 0.0,
        'threshold_mb': max_size_mb,
        'rotated': False,
        'backup_path': None,
        'error': None
    }
    
    try:
        if not db_path.exists():
            result['error'] = 'Database does not exist'
            result['status'] = 'error'
            return result
        
        size_mb = get_db_size_mb(db_path)
        result['size_mb'] = size_mb
        
        if size_mb < max_size_mb:
            result['status'] = 'ok'
            return result
        
        # Size exceeded - rotate!
        print(f"⚠️ Database size ({size_mb:.1f}MB) exceeds threshold ({max_size_mb}MB)")
        print(f"🔄 Rotating database...")
        
        # 1. Create backup
        backup_path = create_backup(db_path, backup_dir)
        print(f"✓ Backup created: {backup_path.name}")
        result['backup_path'] = str(backup_path)
        
        # 2. Initialize fresh database
        init_fresh_database(db_path)
        print(f"✓ Fresh database initialized")
        
        # 3. Log rotation event
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO resonance_notes (timestamp, content, context, source)
            VALUES (datetime('now'), ?, 'system', 'rotation_manager')
        """, (f"Database rotated. Previous size: {size_mb:.1f}MB. Backup: {backup_path.name}",))
        conn.commit()
        conn.close()
        
        result['status'] = 'rotated'
        result['rotated'] = True
        
        print(f"✅ Database rotation complete")
        
    except Exception as e:
        result['status'] = 'error'
        result['error'] = str(e)
        print(f"❌ Rotation error: {e}")
    
    return result


def cleanup_old_backups(backup_dir: Path = None, keep_last: int = 5) -> int:
    """
    Clean up old backups, keeping only the most recent N.
    
    Returns:
        Number of backups deleted
    """
    if backup_dir is None:
        repo_root = Path(__file__).parent.parent
        backup_dir = repo_root / BACKUP_DIR
    
    if not backup_dir.exists():
        return 0
    
    backups = sorted(backup_dir.glob("resonance_*.sqlite3"), key=lambda p: p.stat().st_mtime, reverse=True)
    
    if len(backups) <= keep_last:
        return 0
    
    to_delete = backups[keep_last:]
    deleted_count = 0
    
    for backup in to_delete:
        try:
            backup.unlink()
            print(f"🗑️ Deleted old backup: {backup.name}")
            deleted_count += 1
        except Exception as e:
            print(f"⚠️ Failed to delete {backup.name}: {e}")
    
    return deleted_count


if __name__ == "__main__":
    import sys
    
    print("=" * 60)
    print("🔄 RESONANCE DATABASE ROTATION CHECK")
    print("=" * 60)
    print()
    
    # Check and rotate
    result = check_and_rotate()
    
    print()
    print("📊 STATUS:")
    print(f"   Size: {result['size_mb']:.1f}MB / {result['threshold_mb']}MB")
    print(f"   Status: {result['status'].upper()}")
    
    if result['rotated']:
        print(f"   Backup: {result['backup_path']}")
    
    if result['error']:
        print(f"   Error: {result['error']}")
        sys.exit(1)
    
    # Cleanup old backups
    print()
    print("🗑️ CLEANUP OLD BACKUPS:")
    deleted = cleanup_old_backups(keep_last=5)
    print(f"   Deleted: {deleted} old backup(s)")
    
    print()
    print("✅ Rotation check complete")

