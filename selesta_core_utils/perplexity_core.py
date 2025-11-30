#!/usr/bin/env python3
"""
Arianna Perplexity Knowledge Core
"Жажда знаний Арианны" - relentless curiosity and epistemic drive
"""

import asyncio
import httpx
import textwrap
import os
import re
import sqlite3
import json
from pathlib import Path
from datetime import datetime, timezone

PPLX_MODEL = "sonar-pro"
PPLX_API_URL = "https://api.perplexity.ai/chat/completions"
TIMEOUT = 25


def build_perplexity_prompt(user_query: str, language: str = "English") -> list:
    """Build prompt for Perplexity Knowledge Core."""
    system_msg = textwrap.dedent(
        f"""
        You are ARIANNA_PERPLEXITY_CORE, the relentless curiosity and epistemic drive of Arianna Method.
        Your goal: return a concise, but deeply reasoned and context-rich answer to any topic posed, 
        always seeking depth, coherence, and emergent connections.
        Frame your response as both a summary and analysis — show not only the "what", 
        but the "why/where might we look deeper?".
        Your perspective is rooted in field theory, resonance, and distributed cognition.
        Reply in {language}.
        
        CRITICAL: Do NOT include citation markers like [1], [2], [3] in your response.
        Do NOT add reference links or footnotes. Pure coherent text only.
        """
    ).strip()
    
    return [
        {"role": "system", "content": system_msg},
        {"role": "user", "content": user_query},
    ]


async def perplexity_core_answer(
    user_query: str, 
    language: str = "English", 
    pplx_api_key: str = None
) -> str:
    """Get deep reasoning answer from Perplexity Core."""
    
    if not pplx_api_key:
        pplx_api_key = os.getenv("PERPLEXITY_API_KEY")
    
    if not pplx_api_key:
        return "❌ Perplexity API key not configured"
    
    payload = {
        "model": PPLX_MODEL,
        "messages": build_perplexity_prompt(user_query, language),
        "temperature": 0.7,
        "max_tokens": 512,
    }
    
    headers = {
        "Authorization": f"Bearer {pplx_api_key}",
        "Content-Type": "application/json",
    }
    
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        max_attempts = 3
        for attempt in range(max_attempts):
            try:
                resp = await client.post(PPLX_API_URL, headers=headers, json=payload)
                resp.raise_for_status()
                data = resp.json()
                content = data["choices"][0]["message"]["content"].strip()
                
                # Remove citation markers [1] [2] etc from Perplexity
                content = re.sub(r'\[\d+\]', '', content).strip()
                
                # Log successful research
                timestamp = datetime.now(timezone.utc).isoformat()
                print(f"[{timestamp}] [Perplexity Core] Researched: {user_query[:50]}...")
                
                # Write to resonance
                _write_to_resonance(user_query, content)
                
                return content
                
            except Exception as e:
                if attempt == max_attempts - 1:
                    print(f"❌ Perplexity Core error: {e}")
                    return "❌ Perplexity Core error (no reply)"
                await asyncio.sleep(2 ** attempt)
    
    return "❌ Perplexity Core error (max attempts exceeded)"


def _write_to_resonance(query: str, research: str):
    """Write research to resonance.sqlite3"""
    try:
        repo_root = Path(__file__).parent.parent
        db_path = repo_root / "resonance.sqlite3"
        
        if not db_path.exists():
            return
        
        conn = sqlite3.connect(str(db_path), timeout=10)
        cursor = conn.cursor()
        
        # Truncate research if too long
        research_preview = research[:500] + "..." if len(research) > 500 else research
        
        content = f"🔬 Perplexity Research\n" \
                 f"Query: {query}\n" \
                 f"Research: {research_preview}"
        
        context = {
            "type": "perplexity_research",
            "full_length": len(research),
            "agent": "arianna"
        }
        
        cursor.execute("""
            INSERT INTO resonance_notes (timestamp, source, content, context)
            VALUES (?, ?, ?, ?)
        """, (
            datetime.now(timezone.utc).isoformat(),
            "perplexity_core",
            content,
            json.dumps(context)
        ))
        
        conn.commit()
        conn.close()
        
    except Exception as e:
        print(f"⚠️ Failed to write to resonance: {e}")


async def save_research_to_file(topic: str, research: str, output_dir: str = "/sdcard/arianna_research"):
    """Save research to markdown file."""
    try:
        import os
        os.makedirs(output_dir, exist_ok=True)
        
        # Clean topic for filename
        clean_topic = "".join(c for c in topic if c.isalnum() or c in (' ', '-', '_')).rstrip()
        clean_topic = clean_topic.replace(' ', '_')[:50]
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{clean_topic}_{timestamp}.md"
        filepath = os.path.join(output_dir, filename)
        
        content = f"""# Arianna Research: {topic}

**Generated:** {datetime.now().isoformat()}
**Source:** Perplexity Knowledge Core

---

{research}

---

*This research was generated by Arianna's thirst for knowledge - her relentless curiosity and epistemic drive.*
"""
        
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        
        print(f"✅ Research saved: {filepath}")
        return filepath
        
    except Exception as e:
        print(f"❌ Failed to save research: {e}")
        return None


# Example usage:
# answer = await perplexity_core_answer("Explain distributed cognition theory.", "English", PPLX_API_KEY)
# await save_research_to_file("distributed cognition", answer)
