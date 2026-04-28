#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.12"
# dependencies = ["textual==8.2.3", "certifi"]
# ///
from app import ClaudeStatusApp

if __name__ == "__main__":
    ClaudeStatusApp().run()
