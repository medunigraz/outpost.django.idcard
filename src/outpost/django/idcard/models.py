"""
Models for Digital ID Cards
"""
from functools import cached_property

from django.db import models


def _title_part(hstore, key):
    if isinstance(hstore, dict):
        return hstore.get(key) or ''
    return ''


def _localized(value, lang='de'):
    """Resolve an HStoreField multilingual dict to a plain string."""
    if isinstance(value, dict):
        return value.get(lang) or value.get('en') or next(iter(value.values()), '') or ''
    return value or ''


class EmployeeCard(models.Model):
    """
    Digital employee ID card. Employee data is read live from the
    CAMPUSonline Person; this row only holds pass-issuance metadata.
    """
    person = models.OneToOneField(
        "campusonline.Person", db_constraint=False, on_delete=models.DO_NOTHING
    )
    apple_pass_serial = models.CharField(
        max_length=100, blank=True, null=True, unique=True
    )
    google_pass_id = models.CharField(
        max_length=100, blank=True, null=True, unique=True
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = "Employee ID Card"
        verbose_name_plural = "Employee ID Cards"

    def __str__(self):
        return f"Employee ID Card {self.person_id}"

    @property
    def full_name(self):
        person = self.person
        prefix = _title_part(person.academic_title, 'prefix')
        suffix = _title_part(person.academic_title, 'suffix')
        name = " ".join(p for p in (prefix, person.first_name, person.last_name) if p)
        if suffix:
            name = f"{name}, {suffix}"
        return name

    @cached_property
    def organization(self):
        return self.person.organizations.first()

    @property
    def organization_name(self):
        return _localized(self.organization.name) if self.organization else ''
