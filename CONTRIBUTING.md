# Contributing

Thanks for your interest! This repo accompanies a YouTube video, so the goal is to keep it **simple, readable and safe**.

1. Fork the repo and create a branch.
2. `python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements-dev.txt`
3. Make your change **with a test**, then run `pytest -q`.
4. Open a pull request describing what changed and why.

Out of scope: live-broker order placement, and anything that weakens the risk checks or the paper-trading default.
