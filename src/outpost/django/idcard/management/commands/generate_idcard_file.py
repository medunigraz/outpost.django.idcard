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

    # Override the photo with a local file (when CAMPUSonline has no avatar
    # URL or the download fails)
    python -m django generate_idcard_file <username> --photo ./photo.jpg
"""
import io
import os

import requests
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand, CommandError
from django.db.models import Q
from PIL import Image, UnidentifiedImageError

from outpost.django.idcard.apple_pass import generate_apple_pass
from outpost.django.idcard.models import EmployeeCard
from outpost.django.idcard.sso_views import _avatar_url, _person_to_card_defaults

try:
    from outpost.django.campusonline.models import Person
except ImportError as exc:
    Person = None
    _IMPORT_ERROR = exc
else:
    _IMPORT_ERROR = None


def _is_valid_image_file(path):
    try:
        Image.open(path).verify()
        return True
    except (UnidentifiedImageError, OSError, FileNotFoundError):
        return False


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
        parser.add_argument(
            "--photo",
            metavar="PATH",
            help=(
                "Local image file (jpg/png) to use as the card photo, "
                "overriding whatever CAMPUSonline has. Useful when "
                "person.avatar is empty or the download fails."
            ),
        )

    def handle(self, *args, username, search, output, photo, **options):
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

        self._attach_photo(card, person, photo)

        pass_buffer = generate_apple_pass(card.employee_id, include_signature=True)
        output_path = output or f"./{username}.pkpass"
        with open(output_path, "wb") as f:
            f.write(pass_buffer.getvalue())

        self.stdout.write(self.style.SUCCESS(f"Wrote {output_path}"))

    def _attach_photo(self, card, person, photo_path):
        if photo_path:
            if not os.path.exists(photo_path):
                raise CommandError(f"--photo file does not exist: {photo_path}")
            with open(photo_path, "rb") as f:
                content = f.read()
            filename = os.path.basename(photo_path)
            card.photo.save(filename, ContentFile(content, name=filename), save=True)
            self.stdout.write(self.style.SUCCESS(
                f"Attached local photo: {photo_path} ({len(content)} bytes)"
            ))
            return

        avatar_url = _avatar_url(person)
        self.stdout.write(
            f"avatar_private={getattr(person, 'avatar_private', None)!r} "
            f"avatar={person.avatar!r} → using {avatar_url!r}"
        )

        if card.photo:
            if _is_valid_image_file(card.photo.path):
                self.stdout.write(f"Using already-stored photo: {card.photo.name}")
                return
            self.stdout.write(self.style.WARNING(
                f"Stored photo {card.photo.name} is not a valid image — "
                f"discarding and re-fetching."
            ))
            card.photo.delete(save=True)

        if not avatar_url:
            self.stdout.write(self.style.WARNING(
                "No avatar URL in CAMPUSonline — pass will use the "
                "silhouette placeholder. To attach a real photo manually, "
                "re-run with --photo /path/to/photo.jpg"
            ))
            return

        try:
            response = requests.get(avatar_url, timeout=10)
            response.raise_for_status()
        except requests.RequestException as exc:
            self.stdout.write(self.style.WARNING(
                f"Avatar download from {avatar_url} failed: {exc}\n"
                f"Pass will use the silhouette placeholder. To attach a "
                f"real photo manually, re-run with --photo /path/to/photo.jpg"
            ))
            return

        content_type = response.headers.get("Content-Type", "?")
        try:
            Image.open(io.BytesIO(response.content)).verify()
        except (UnidentifiedImageError, OSError) as exc:
            preview = response.content[:200]
            self.stdout.write(self.style.WARNING(
                f"Avatar URL returned {len(response.content)} bytes with "
                f"Content-Type {content_type!r}, but it's not a valid image: "
                f"{exc}\n"
                f"First bytes: {preview!r}\n"
                f"Most likely the endpoint is session-gated and returned an "
                f"HTML login page instead of the image. Pass will use the "
                f"silhouette placeholder. Re-run with --photo /path/to/photo.jpg "
                f"to attach one manually."
            ))
            return

        filename = person.avatar.rsplit("/", 1)[-1] or f"employee_{person.id}.jpg"
        card.photo.save(filename, ContentFile(response.content, name=filename), save=True)
        self.stdout.write(self.style.SUCCESS(
            f"Downloaded photo from CAMPUSonline "
            f"({len(response.content)} bytes, Content-Type {content_type!r})"
        ))

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
