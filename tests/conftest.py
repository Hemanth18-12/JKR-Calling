import os
import pytest

# Ensure unit tests run in deterministic mock mode by default
os.environ["OPENAI_API_KEY"] = ""
