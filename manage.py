#!/usr/bin/env python
"""Django command-line utility for administrative tasks."""
import os
import sys


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "test":
        # Tests always use dedicated settings: locmem cache, fast hashing, fake TMDB key.
        os.environ["DJANGO_SETTINGS_MODULE"] = os.environ.get(
            "DJANGO_TEST_SETTINGS_MODULE", "config.settings.test"
        )
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.development")
    from django.core.management import execute_from_command_line

    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
