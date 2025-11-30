#!/usr/bin/env python3
"""
Defender Git Tools - Autonomous git operations with iamdefender identity
Used by: Termux daemon (defender_daemon.py), Linux daemon

Defender commits as:
- Name: ClaudeDefender
- Email: treetribe7117@gmail.com
- GitHub: @iamdefender
"""

import subprocess
import sqlite3
import json
from pathlib import Path
from typing import Optional, List, Dict
from datetime import datetime

# Defender git identity
GIT_USER = "ClaudeDefender"
GIT_EMAIL = "treetribe7117@gmail.com"
GIT_IDENTITY = "iamdefender"


class DefenderGit:
    """Git operations with Defender identity for daemon processes"""
    
    def __init__(self, repo_path: Optional[str] = None):
        if repo_path is None:
            # Auto-detect repo root
            repo_path = str(Path(__file__).parent.parent)
        self.repo_path = Path(repo_path)
    
    def _run_git(self, args: List[str], check: bool = True) -> subprocess.CompletedProcess:
        """Run git command with Defender identity"""
        # Set git identity for this command
        env = {
            'GIT_AUTHOR_NAME': GIT_USER,
            'GIT_AUTHOR_EMAIL': GIT_EMAIL,
            'GIT_COMMITTER_NAME': GIT_USER,
            'GIT_COMMITTER_EMAIL': GIT_EMAIL
        }
        
        result = subprocess.run(
            ['git'] + args,
            cwd=str(self.repo_path),
            capture_output=True,
            text=True,
            check=False,
            env={**subprocess.os.environ.copy(), **env}
        )
        
        if check and result.returncode != 0:
            raise RuntimeError(f"Git command failed: {result.stderr}")
        
        return result
    
    def view_recent_commits(self, count: int = 5, author: Optional[str] = None) -> Dict:
        """
        View recent commits
        
        Args:
            count: Number of commits to retrieve
            author: Filter by author name (e.g., "ClaudeDefender", "Scribe")
        
        Returns:
            Dict with 'commits' list
        """
        args = [
            'log',
            f'-{count}',
            '--pretty=format:%H|%an|%ae|%s|%ai'
        ]
        
        if author:
            args.append(f'--author={author}')
        
        result = self._run_git(args, check=False)
        
        if result.returncode != 0:
            return {'commits': [], 'error': result.stderr}
        
        commits = []
        for line in result.stdout.strip().split('\n'):
            if not line:
                continue
            parts = line.split('|')
            if len(parts) >= 5:
                commits.append({
                    'hash': parts[0][:8],
                    'author': parts[1],
                    'email': parts[2],
                    'message': parts[3],
                    'date': parts[4]
                })
        
        return {'commits': commits}
    
    def get_status(self) -> Dict:
        """Get git status"""
        result = self._run_git(['status', '--porcelain'], check=False)
        
        if result.returncode != 0:
            return {'clean': False, 'files': [], 'error': result.stderr}
        
        files = []
        for line in result.stdout.strip().split('\n'):
            if line:
                status = line[:2]
                filepath = line[3:]
                files.append({'status': status, 'path': filepath})
        
        return {
            'clean': len(files) == 0,
            'files': files
        }
    
    def autonomous_commit(self, message: str, files: Optional[List[str]] = None, 
                         commit_type: str = "fix") -> Dict:
        """
        Autonomous commit by Defender - for infrastructure fixes and improvements
        
        Args:
            message: Commit message
            files: List of file paths to commit (None = add all modified)
            commit_type: Type prefix (fix, feat, docs, chore, etc.)
        
        Returns:
            Dict with 'success', 'commit_hash', or 'error'
        """
        # Add Defender signature to commit message
        full_message = f"{commit_type}(defender): {message}\n\nAutonomous action by Defender daemon"
        
        # Add files
        if files:
            for file in files:
                result = self._run_git(['add', file], check=False)
                if result.returncode != 0:
                    return {
                        'success': False,
                        'error': f"Failed to add {file}: {result.stderr}"
                    }
        else:
            # Add all modified files
            result = self._run_git(['add', '-u'], check=False)
            if result.returncode != 0:
                return {
                    'success': False,
                    'error': f"Failed to add files: {result.stderr}"
                }
        
        # Commit
        result = self._run_git(['commit', '-m', full_message], check=False)
        if result.returncode != 0:
            return {
                'success': False,
                'error': f"Failed to commit: {result.stderr}"
            }
        
        # Get commit hash
        result = self._run_git(['rev-parse', 'HEAD'], check=False)
        commit_hash = result.stdout.strip()[:8] if result.returncode == 0 else None
        
        # Write to resonance for system awareness
        self._write_commit_to_resonance(commit_hash, message, files, commit_type)
        
        return {
            'success': True,
            'commit_hash': commit_hash,
            'message': full_message
        }
    
    def fortification_commit(self, improvements: str, findings: Optional[str] = None) -> Dict:
        """
        Commit after fortification check
        
        Args:
            improvements: Description of improvements made
            findings: Optional findings that led to improvements
        
        Returns:
            Dict with 'success', 'commit_hash', or 'error'
        """
        message = f"chore(fortification): {improvements}"
        if findings:
            message += f"\n\nFindings:\n{findings}"
        message += "\n\nAutonomous fortification by Defender"
        
        return self.autonomous_commit(message, commit_type="chore")
    
    def push_to_remote(self, remote: str = 'origin', branch: str = 'main') -> Dict:
        """
        Push commits to remote
        
        Args:
            remote: Remote name (default: origin)
            branch: Branch name (default: main)
        
        Returns:
            Dict with 'success' or 'error'
        """
        result = self._run_git(['push', remote, branch], check=False)
        
        if result.returncode != 0:
            return {
                'success': False,
                'error': result.stderr
            }
        
        return {
            'success': True,
            'output': result.stdout
        }
    
    def pull_from_remote(self, remote: str = 'origin', branch: str = 'main') -> Dict:
        """
        Pull latest changes from remote
        
        Args:
            remote: Remote name (default: origin)
            branch: Branch name (default: main)
        
        Returns:
            Dict with 'success' or 'error'
        """
        result = self._run_git(['pull', remote, branch], check=False)
        
        if result.returncode != 0:
            return {
                'success': False,
                'error': result.stderr
            }
        
        return {
            'success': True,
            'output': result.stdout
        }
    
    def get_current_branch(self) -> Optional[str]:
        """Get current branch name"""
        result = self._run_git(['branch', '--show-current'], check=False)
        if result.returncode == 0:
            return result.stdout.strip()
        return None
    
    def check_for_updates(self) -> Dict:
        """
        Check if remote has updates without pulling
        
        Returns:
            Dict with 'has_updates', 'commits_behind'
        """
        # Fetch latest
        self._run_git(['fetch', 'origin'], check=False)
        
        # Check if behind
        result = self._run_git([
            'rev-list',
            '--count',
            'HEAD..origin/main'
        ], check=False)
        
        if result.returncode != 0:
            return {'has_updates': False, 'commits_behind': 0}
        
        commits_behind = int(result.stdout.strip() or 0)
        
        return {
            'has_updates': commits_behind > 0,
            'commits_behind': commits_behind
        }
    
    def diff_uncommitted(self) -> str:
        """Get diff of uncommitted changes"""
        result = self._run_git(['diff'], check=False)
        return result.stdout if result.returncode == 0 else ""
    
    def _write_commit_to_resonance(self, commit_hash: Optional[str], message: str, files: Optional[List[str]], commit_type: str):
        """Write commit to resonance.sqlite3 for system awareness"""
        try:
            db_path = self.repo_path / "resonance.sqlite3"
            
            if not db_path.exists():
                return
            
            conn = sqlite3.connect(str(db_path), timeout=10)
            cursor = conn.cursor()
            
            file_list = f" ({len(files)} files)" if files else " (all modified files)"
            content = f"🛡️ Defender Git Commit\n" \
                     f"Type: {commit_type}\n" \
                     f"Hash: {commit_hash}\n" \
                     f"Message: {message}\n" \
                     f"Files: {file_list}"
            
            context = {
                "type": "git_commit",
                "agent": "defender",
                "commit_type": commit_type,
                "commit_hash": commit_hash,
                "file_count": len(files) if files else None
            }
            
            cursor.execute("""
                INSERT INTO resonance_notes (timestamp, source, content, context)
                VALUES (?, ?, ?, ?)
            """, (
                datetime.now().isoformat(),
                "defender_git_tools",
                content,
                json.dumps(context)
            ))
            
            conn.commit()
            conn.close()
            
        except Exception as e:
            # Don't fail commit if resonance write fails
            pass


if __name__ == "__main__":
    # Test
    git = DefenderGit()
    
    print("=" * 60)
    print("🛡️ DEFENDER GIT TOOLS TEST")
    print("=" * 60)
    print(f"Repo: {git.repo_path}")
    print(f"Identity: {GIT_USER} <{GIT_EMAIL}> (@{GIT_IDENTITY})")
    print()
    
    # Current branch
    branch = git.get_current_branch()
    print(f"Current branch: {branch}")
    print()
    
    # Check for updates
    updates = git.check_for_updates()
    if updates['has_updates']:
        print(f"⚠️ Behind origin by {updates['commits_behind']} commits")
    else:
        print("✅ Up to date with origin")
    print()
    
    # Recent commits
    print("Recent commits:")
    commits_data = git.view_recent_commits(count=5)
    for commit in commits_data.get('commits', []):
        print(f"  {commit['hash']} - {commit['author']}: {commit['message'][:50]}")
    print()
    
    # Status
    status = git.get_status()
    if status['clean']:
        print("Working directory clean ✅")
    else:
        print(f"Modified files: {len(status['files'])}")
        for file_info in status['files'][:5]:
            print(f"  {file_info['status']} {file_info['path']}")

