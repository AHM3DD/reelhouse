import time

from django.core.management.base import BaseCommand, CommandError
from django.db import connections
from django.db.utils import OperationalError


class Command(BaseCommand):
    help = "Block until the default database accepts connections (or the timeout expires)."

    def add_arguments(self, parser):
        parser.add_argument("--timeout", type=int, default=60, help="Seconds to wait before failing.")
        parser.add_argument("--interval", type=float, default=1.5, help="Seconds between attempts.")

    def handle(self, *args, timeout, interval, **options):
        deadline = time.monotonic() + timeout
        attempt = 0
        while True:
            attempt += 1
            connection = connections["default"]
            try:
                connection.ensure_connection()
                self.stdout.write(self.style.SUCCESS(f"Database available (attempt {attempt})."))
                return
            except OperationalError:
                connection.close()
                if time.monotonic() >= deadline:
                    raise CommandError(f"Database unavailable after {timeout}s.")
                self.stdout.write(f"Waiting for database... (attempt {attempt})")
                time.sleep(interval)
