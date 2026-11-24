import os
from pathlib import Path

def load_env_file(dotenv_path: Path = None):
    """
    Lightweight .env loader that works independently of python-dotenv.
    Reads KEY=VALUE lines into os.environ.
    """
    if dotenv_path is None:
        dotenv_path = Path(__file__).resolve().parents[1] / ".env"
        
    if not dotenv_path.exists():
        return

    with open(dotenv_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, val = line.split("=", 1)
            key = key.strip()
            val = val.strip().strip("'\"")
            if key and key not in os.environ:
                os.environ[key] = val
