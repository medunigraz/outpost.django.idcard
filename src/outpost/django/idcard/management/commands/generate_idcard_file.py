"""
Admin command: generate a signed .pkpass file for a CAMPUSonline user and
write it to disk. Use this when an admin needs to hand a card to someone
directly instead of relying on the self-service SSO flow at /idcard/my-pass/.

Usage:
    # Look people up by name fragment (case-insensitive match on first/last name)
    python -m django generate_idcard_file --search Surname

    # Generate the file for a known username (defaults to ./<username>.pkpass)
    python -m django generate_idcard_file <username>
    python -m django generate_idcard_file <username> --output /tmp/card.pkpass
"""

from django.core.management.base import (
    BaseCommand,
    CommandError,
)
from django.db.models import Q
from outpost.django.campusonline.models import Person

from outpost.django.idcard.models import EmployeeCard


class Command(BaseCommand):
    help = (
        "Generate a signed .pkpass file for a CAMPUSonline user and write "
        "it to disk. Use --search to look up usernames by name."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "username",
            nargs="?",
            help="CAMPUSonline username to generate the pass for.",
        )
        parser.add_argument(
            "--search",
            metavar="NAME",
            help=(
                "Print all employed people whose first or last name contains "
                "NAME (case-insensitive), with their usernames. Use this to "
                "look up a colleague's username before generating their pass."
            ),
        )
        parser.add_argument(
            "--output",
            metavar="PATH",
            help="Where to write the .pkpass (default: ./<username>.pkpass).",
        )

    def handle(self, *args, username, search, output, **options):
        if search:
            self._do_search(search)
            return

        if not username:
            raise CommandError(
                "Provide a username, or use --search NAME to look one up."
            )

        try:
            person = Person.objects.get(username=username)
        except Person.DoesNotExist:
            raise CommandError(
                f"No CAMPUSonline person with username {username!r}. "
                f"Use --search to look up names."
            )

        if not person.employed:
            raise CommandError(
                f"{username!r} is not currently employed. "
                f"Digital ID cards are only issued to active staff."
            )

        card, created = EmployeeCard.objects.get_or_create(person=person)
        action = "Created" if created else "Found"
        self.stdout.write(
            f"{action} EmployeeCard for {person.first_name} {person.last_name} "
            f"(Bedienstetennummer {person.id})."
        )

        if not person.hash:
            self.stdout.write(
                self.style.WARNING(
                    "No photo in CAMPUSonline, the pass will use the silhouette."
                )
            )

        output_path = output or f"./{username}.pkpass"
        with open(output_path, "wb") as f:
            f.write(card.apple_pass())

        self.stdout.write(self.style.SUCCESS(f"Wrote {output_path}"))

    def _do_search(self, name):
        qs = Person.objects.filter(
            Q(first_name__icontains=name) | Q(last_name__icontains=name),
            employed=True,
        ).order_by("last_name", "first_name")[:50]

        if not qs:
            self.stdout.write(f"No employed person matches {name!r}.")
            return

        self.stdout.write(f"{'Username':<20} {'Name':<40} {'OE'}")
        self.stdout.write("-" * 80)
        for p in qs:
            org = p.organizations.first()
            org_short = (org.short or "") if org else ""
            self.stdout.write(
                f"{p.username:<20} {p.first_name} {p.last_name:<40} {org_short}"
            )
        if qs.count() == 50:
            self.stdout.write(
                self.style.WARNING("(truncated at 50 results, refine your search)")
            )
