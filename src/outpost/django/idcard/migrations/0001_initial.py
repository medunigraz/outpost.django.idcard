import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("campusonline", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="EmployeeCard",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "apple_pass_serial",
                    models.CharField(
                        blank=True, max_length=100, null=True, unique=True
                    ),
                ),
                (
                    "google_pass_id",
                    models.CharField(
                        blank=True, max_length=100, null=True, unique=True
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "person",
                    models.OneToOneField(
                        db_constraint=False,
                        on_delete=django.db.models.deletion.DO_NOTHING,
                        to="campusonline.person",
                    ),
                ),
            ],
            options={
                "verbose_name": "Employee ID Card",
                "verbose_name_plural": "Employee ID Cards",
                "ordering": ["-created_at"],
            },
        ),
    ]
