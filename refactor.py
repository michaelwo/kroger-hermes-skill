#!/usr/bin/env python3
"""
Refactor kroger_shopping code using Codex Universal.
Usage: python refactor.py <file_or_module>
"""

import sys
import os
from pathlib import Path

# Add codex-universal to path
sys.path.insert(0, '/opt/codex-universal')

from codex_universal import Codex

def refactor_file(filepath: str):
    """Refactor a Python file using Codex."""
    
    if not os.path.exists(filepath):
        print(f"File not found: {filepath}")
        return
    
    with open(filepath, 'r') as f:
        code = f.read()
    
    api_key = os.getenv('OPENAI_API_KEY')
    if not api_key:
        print("Error: OPENAI_API_KEY not set")
        return
    
    codex = Codex(api_key=api_key)
    
    prompt = f"""Refactor the following Python code for clarity, performance, and maintainability:

{code}

Provide the refactored code with explanations of changes."""
    
    print(f"Refactoring {filepath}...")
    result = codex.run(prompt)
    print("\n" + "="*80)
    print(result)
    print("="*80)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python refactor.py <file_path>")
        print("Example: python refactor.py kroger_shopping/client.py")
        sys.exit(1)
    
    refactor_file(sys.argv[1])
