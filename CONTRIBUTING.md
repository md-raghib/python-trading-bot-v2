# Contributing

Thanks for your interest! This repo accompanies a YouTube video and is maintained by its author only, so **pull requests are not accepted**.

You can still help:

- **Found a bug?** Open a [bug report](../../issues/new?template=bug_report.md).
- **Have an idea or a strategy for a future video?** Open a [feature request](../../issues/new?template=feature_request.md).
- **Security problem?** Report it privately, see [SECURITY.md](SECURITY.md).
- **Want to experiment?** Fork the repo and change your copy however you like (MIT license).

## Running it locally

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
pytest -q
```
