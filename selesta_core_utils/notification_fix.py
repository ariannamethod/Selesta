#!/usr/bin/env python3
"""
Fix for Genesis notifications - create readable text files in /sdcard/
that can be opened with any text editor when tapped.
"""

import subprocess
from pathlib import Path

def send_openable_notification(title: str, content: str, icon: str = "✨"):
    """
    Send notification with text file that opens in external editor.
    Works better than --action which is buggy.
    """
    # Create readable file in /sdcard/
    filename = f"genesis_{icon.replace('✨', 'arianna').replace('💀', 'monday')}.txt"
    filepath = Path(f"/storage/emulated/0/{filename}")

    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(f"{icon} {title}\n")
        f.write("=" * 60 + "\n\n")
        f.write(content)
        f.write("\n\n" + "=" * 60 + "\n")
        f.write(f"\nSaved to: {filepath}\n")

    # Preview for notification
    preview = content[:180] + "..." if len(content) > 180 else content

    # Send notification with button to open file
    try:
        subprocess.run([
            "termux-notification",
            "-t", f"{icon} {title}",
            "-c", preview,
            "--priority", "default",
            "--button1", "📖 Read Full",
            "--button1-action", f"termux-open {filepath}"
        ], check=True, capture_output=True)

        return True
    except Exception as e:
        print(f"Failed to send notification: {e}")
        return False


if __name__ == "__main__":
    # Test
    send_openable_notification(
        "Genesis-Arianna",
        "Test message from Arianna Method notification fixer.",
        "✨"
    )
