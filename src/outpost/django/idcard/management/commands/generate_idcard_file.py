"""
Generate a signed .pkpass file for a specific CAMPUSonline user and write it
to disk. Use this to hand out test cards to colleagues before the SSO flow
is publicly available (or where you want to hand someone the file directly
without them going through the web flow).

Usage:
    # Look people up by name fragment (case-insensitive match on first/last name)
    python -m django generate_idcard_file --search Surname

    # Generate the file for a known username (defaults to ./<username>.pkpass)
    python -m django generate_idcard_file o_name
    python -m django generate_idcard_file o_name --output /tmp/name.pkpass
"""
from django.core.management.base import BaseCommand, CommandError
from django.db.models import Q

from outpost.django.idcard.apple_pass import generate_apple_pass
from outpost.django.idcard.models import EmployeeCard
from outpost.django.idcard.sso_views import (
    _person_to_card_defaults,
    download_avatar,
)

try:
    from outpost.django.campusonline.models import Person
except ImportError as exc:
    Person = None
    _IMPORT_ERROR = exc
else:
    _IMPORT_ERROR = None


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
        if Person is None:
            raise CommandError(
                f"outpost.django.campusonline is not importable: {_IMPORT_ERROR}"
            )

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

        card, created = EmployeeCard.objects.update_or_create(
            employee_id=person.id,
            defaults=_person_to_card_defaults(person),
        )
        action = "Created" if created else "Refreshed"
        self.stdout.write(
            f"{action} EmployeeCard for {person.first_name} {person.last_name} "
            f"(Bedienstetennummer {person.id})."
        )

        if person.avatar and not card.photo:
            avatar_file = download_avatar(person.avatar)
            if avatar_file:
                card.photo.save(
                    f"employee_{person.id}.jpg",
                    avatar_file,
                    save=True,
                )
                self.stdout.write("Downloaded photo from CAMPUSonline.")
            else:
                self.stdout.write(self.style.WARNING(
                    "Could not download avatar — pass will have no photo."
                ))

        pass_buffer = generate_apple_pass(card.employee_id, include_signature=True)
        output_path = output or f"./{username}.pkpass"
        with open(output_path, "wb") as f:
            f.write(pass_buffer.getvalue())

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
            self.stdout.write(self.style.WARNING(
                "(truncated at 50 results — refine your search)"
            ))
