"""
Models for Digital ID Cards
"""
from django.db import models


class EmployeeCard(models.Model):
    """
    Digital employee ID card model.
    Stores all information needed to generate Apple Wallet and Google Wallet passes.
    """
    # Basic employee information
    employee_id = models.IntegerField(unique=True, help_text="Unique employee ID number")
    first_name = models.CharField(max_length=200)
    last_name = models.CharField(max_length=200)
    
    # Organizational information
    organizational_unit = models.CharField(
        max_length=300, 
        blank=True,
        help_text="Employee's organizational unit (OE)"
    )
    
    # Photo for visual identification
    photo = models.ImageField(
        upload_to='employee_photos/',
        blank=True,
        null=True,
        help_text="Employee photo for ID card"
    )
    
    # QR code data - links to employee's Visitenkarte (business card)
    visitenkarte_url = models.URLField(
        max_length=500,
        blank=True,
        help_text="URL to employee's online business card (Visitenkarte)"
    )
    
    # Pass generation metadata
    apple_pass_serial = models.CharField(
        max_length=100, 
        blank=True,
        null=True,
        unique=True,
        help_text="Serial number for Apple Wallet pass"
    )
    google_pass_id = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        unique=True,
        help_text="ID for Google Wallet pass"
    )
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
        verbose_name = "Employee ID Card"
        verbose_name_plural = "Employee ID Cards"
    
    def __str__(self):
        return f"{self.first_name} {self.last_name} ({self.employee_id})"
    
    @property
    def full_name(self):
        """Return the employee's full name"""
        return f"{self.first_name} {self.last_name}"