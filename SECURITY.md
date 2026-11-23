# Security policy

## Reporting a vulnerability

Please **do not open a public issue** for security problems.

Use GitHub's private reporting instead: **Security → Report a vulnerability** on this repository.
You'll get a reply as soon as possible.

## Keeping your own setup safe

- Never commit `.env`, API keys, broker tokens or Telegram tokens. `.env` is git-ignored for this reason.
- This project trades on paper only. If you add a live broker yourself, keep credentials in environment variables or a secret manager, and keep paper mode as the default.
