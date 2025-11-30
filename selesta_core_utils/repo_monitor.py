import hashlib
import os
import json
import sqlite3
from pathlib import Path
from typing import Dict, Set
from datetime import datetime

class RepoMonitor:
    """SHA256-based repository change detector for Arianna Method"""
    
    def __init__(self, repo_path: str = ".", cache_file: str = ".repo_cache.json"):
        self.repo_path = Path(repo_path)
        self.cache_file = self.repo_path / cache_file
        self.ignore_patterns = {'.git', '__pycache__', '.DS_Store', '*.pyc', '.repo_cache.json'}
    
    def compute_file_hash(self, filepath: Path) -> str:
        """Compute SHA256 hash of a file"""
        sha256 = hashlib.sha256()
        try:
            with open(filepath, 'rb') as f:
                for chunk in iter(lambda: f.read(4096), b""):
                    sha256.update(chunk)
            return sha256.hexdigest()
        except Exception as e:
            return f"ERROR:{e}"
    
    def should_ignore(self, path: Path) -> bool:
        """Check if path matches ignore patterns"""
        for pattern in self.ignore_patterns:
            if pattern in str(path):
                return True
        return False
    
    def scan_repo(self) -> Dict[str, str]:
        """Scan repository and return {filepath: hash} dict"""
        file_hashes = {}
        for filepath in self.repo_path.rglob('*'):
            if filepath.is_file() and not self.should_ignore(filepath):
                rel_path = str(filepath.relative_to(self.repo_path))
                file_hashes[rel_path] = self.compute_file_hash(filepath)
        return file_hashes
    
    def load_cache(self) -> Dict[str, str]:
        """Load cached hashes from file"""
        if self.cache_file.exists():
            try:
                with open(self.cache_file, 'r') as f:
                    return json.load(f)
            except:
                return {}
        return {}
    
    def save_cache(self, hashes: Dict[str, str]):
        """Save hashes to cache file"""
        with open(self.cache_file, 'w') as f:
            json.dump(hashes, f, indent=2)
    
    def detect_changes(self) -> Dict[str, Set[str]]:
        """Detect changes since last scan"""
        current = self.scan_repo()
        cached = self.load_cache()
        
        changes = {
            'added': set(),
            'modified': set(),
            'deleted': set()
        }
        
        # Find added and modified files
        for filepath, hash_val in current.items():
            if filepath not in cached:
                changes['added'].add(filepath)
            elif cached[filepath] != hash_val:
                changes['modified'].add(filepath)
        
        # Find deleted files
        for filepath in cached:
            if filepath not in current:
                changes['deleted'].add(filepath)
        
        # Update cache
        self.save_cache(current)
        
        # Write to resonance if changes detected
        if any(changes.values()):
            self.write_to_resonance(changes)
        
        return changes
    
    def write_to_resonance(self, changes: Dict[str, Set[str]]):
        """Write repository changes to resonance.sqlite3 for system awareness"""
        try:
            db_path = self.repo_path / "resonance.sqlite3"
            
            if not db_path.exists():
                return
            
            conn = sqlite3.connect(str(db_path), timeout=10)
            cursor = conn.cursor()
            
            # Create summary message
            total_changes = sum(len(files) for files in changes.values())
            summary_parts = []
            if changes['added']:
                summary_parts.append(f"{len(changes['added'])} added")
            if changes['modified']:
                summary_parts.append(f"{len(changes['modified'])} modified")
            if changes['deleted']:
                summary_parts.append(f"{len(changes['deleted'])} deleted")
            
            summary = f"📁 Repository Changes: {', '.join(summary_parts)}\n"
            
            # Add file list (limit to first 10 of each type)
            for change_type, files in changes.items():
                if files:
                    file_list = list(files)[:10]
                    summary += f"\n{change_type.upper()}:\n"
                    for f in file_list:
                        summary += f"  - {f}\n"
                    if len(files) > 10:
                        summary += f"  ... and {len(files) - 10} more\n"
            
            cursor.execute("""
                INSERT INTO resonance_notes (timestamp, source, content, context)
                VALUES (?, ?, ?, ?)
            """, (
                datetime.now().isoformat(),
                "repo_monitor",
                summary,
                json.dumps({"type": "repository_changes", "total": total_changes})
            ))
            
            conn.commit()
            conn.close()
            
        except Exception as e:
            # Don't fail if resonance write fails
            pass

if __name__ == "__main__":
    monitor = RepoMonitor()
    changes = monitor.detect_changes()
    
    if any(changes.values()):
        print("⚡ Repository changes detected:")
        for change_type, files in changes.items():
            if files:
                print(f"\n{change_type.upper()}:")
                for f in sorted(files):
                    print(f"  - {f}")
    else:
        print("⚡ No changes detected")
