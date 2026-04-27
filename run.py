#!/usr/bin/env python3
import subprocess
import sys

if __name__ == "__main__":
    subprocess.run([sys.executable, "-m", "solara", "run", "app.py", "--port", "8765"])
