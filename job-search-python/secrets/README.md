# Secrets Directory

This folder contains local-only runtime secrets used by batch scripts for loggin into sites.

## Files expected by scripts

- `secrets/www.glassdoor.com.env`
- `secrets/www.linkedin.com.env`
- ...

Create each file from its `.example` template and replace placeholders before running scripts.

## Notes

- Do not commit real secrets.
- `.env` files are ignored by git via `.gitignore`.
- Keep keys in `KEY=value` format, one per line.
- Lines starting with `#` are treated as comments.
