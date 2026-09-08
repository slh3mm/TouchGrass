from datetime import date

from django.core.management.base import BaseCommand, CommandError

from worldtravel.uat import ANCHOR_DATE, UATConfigurationError, prepare, write_manifest


class Command(BaseCommand):
    help = "Scrub a cloned database and seed the isolated TouchGrass UAT environment."

    def add_arguments(self, parser):
        parser.add_argument("--manifest", required=True, help="Destination for the sanitized JSON manifest")
        parser.add_argument("--reset", action="store_true", help="Replace generated [UAT] records before seeding")
        parser.add_argument(
            "--anchor-date",
            default=ANCHOR_DATE.isoformat(),
            help="Frozen UAT reference date (YYYY-MM-DD)",
        )
        parser.add_argument("--scenario", choices=("core", "stress", "all"), default="all")
        parser.add_argument(
            "--owner-username",
            help="Existing cloned owner to anonymize as uat-owner while preserving owned travel data",
        )
        parser.add_argument(
            "--password",
            help="Common fallback password; per-account UAT_*_PASSWORD variables take precedence",
        )

    def handle(self, *args, **options):
        try:
            anchor = date.fromisoformat(options["anchor_date"])
        except ValueError as exc:
            raise CommandError("--anchor-date must use YYYY-MM-DD") from exc
        try:
            manifest, generated_passwords = prepare(
                owner_username=options.get("owner_username"),
                common_password=options.get("password"),
                anchor=anchor,
                scenario=options["scenario"],
                reset=options["reset"],
            )
            write_manifest(manifest, options["manifest"])
        except UATConfigurationError as exc:
            raise CommandError(str(exc)) from exc

        self.stdout.write(self.style.SUCCESS(f"Prepared {options['scenario']} UAT data"))
        self.stdout.write(f"Sanitized manifest: {options['manifest']}")
        if generated_passwords:
            self.stdout.write(self.style.WARNING("Generated one-time UAT passwords (not written to manifest):"))
            for role, password in generated_passwords.items():
                self.stdout.write(f"  uat-{role}: {password}")
