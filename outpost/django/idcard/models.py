"""
Models for Digital ID Cards
"""
from django.db import models


class EmployeeCard(models.Model):
    """
    Simple model to test the foundation.
    Just stores basic employee info for now.
    """
    employee_id = models.IntegerField(unique=True)
    first_name = models.CharField(max_length=200)
    last_name = models.CharField(max_length=200)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.first_name} {self.last_name} ({self.employee_id})"
