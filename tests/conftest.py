import os
from dotenv import load_dotenv
import pytest

load_dotenv()

# Ensure unit tests run in deterministic mock mode by default
os.environ["OPENAI_API_KEY"] = ""

