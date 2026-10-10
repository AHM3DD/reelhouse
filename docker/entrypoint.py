#!/usr/bin/env python
"""Container entrypoint: wait for PostgreSQL, apply migrations, then exec the command.

Written in Python rather than sh so it keeps working when the source tree is
bind-mounted from a Windows host with CRLF line endings.
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)


def env_flag(name, default):
    return os.environ.get(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


def main():
    if len(sys.argv) < 2:
        print("entrypoint: no command given", file=sys.stderr)
        sys.exit(2)

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.development")
    import django

    django.setup()
    from django.core.management import call_command

    call_command("wait_for_db")
    if env_flag("DJANGO_MIGRATE_ON_START", True):
        call_command("migrate", interactive=False, verbosity=1)
        call_command("createcachetable")

    os.execvp(sys.argv[1], sys.argv[1:])


if __name__ == "__main__":
    main()
