"""
Models for Digital ID Cards
"""
from django.db import models


class EmployeeCard(models.Model):
    """
    Digital employee ID card. Mirrors a subset of CAMPUSonline data needed
    to generate Apple Wallet and Google Wallet passes, plus pass-issuance
    metadata (serial numbers, timestamps).
    """
    # Identity — employee_id IS the CAMPUSonline Person.id (Bedienstetennummer)
    employee_id = models.IntegerField(
        unique=True,
        help_text="Bedienstetennummer (CAMPUSonline Person ID)",
    )
    first_name = models.CharField(max_length=200)
    last_name = models.CharField(max_length=200)
    title_prefix = models.CharField(max_length=200, blank=True)
    title_suffix = models.CharField(max_length=200, blank=True)
    email = models.EmailField(max_length=254, blank=True)

    # Organisation
    organizational_unit = models.CharField(
        max_length=300,
        blank=True,
        help_text="Full OE name, German",
    )
    organizational_unit_short = models.CharField(
        max_length=32,
        blank=True,
        help_text="OE short code (e.g. O-IT)",
    )
    dienstort = models.CharField(
        max_length=300,
        blank=True,
        help_text="Work address (Organization.address)",
    )
    organization_phone = models.CharField(max_length=64, blank=True)
    organization_email = models.EmailField(max_length=254, blank=True)

    # Photo + QR target
    photo = models.ImageField(
        upload_to='employee_photos/',
        blank=True,
        null=True,
        help_text="Employee photo for ID card",
    )
    visitenkarte_url = models.URLField(
        max_length=500,
        blank=True,
        help_text="Online business card URL — encoded in the QR",
    )

    # Pass identifiers
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
        return f"{self.full_name} ({self.employee_id})"

    @property
    def full_name(self):
        parts = [self.title_prefix, self.first_name, self.last_name, self.title_suffix]
        return " ".join(p for p in parts if p)
