import django.db.models.deletion
from django.db import (
    migrations,
    models,
)


class Migration(migrations.Migration):

    dependencies = [
        ("idcard", "0002_employeecard_options"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="employeecard",
            options={
                "ordering": ("-created_at",),
                "permissions": (
                    (
                        "manage_passes",
                        "Can download, re-push and revoke any employee's passes",
                    ),
                ),
                "verbose_name": "Employee ID card",
                "verbose_name_plural": "Employee ID cards",
            },
        ),
        migrations.AddField(
            model_name="employeecard",
            name="apple_auth_token",
            field=models.CharField(blank=True, max_length=64, null=True),
        ),
        migrations.AddField(
            model_name="employeecard",
            name="pass_hash",
            field=models.CharField(blank=True, max_length=40, null=True),
        ),
        migrations.AddField(
            model_name="employeecard",
            name="pass_updated_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="employeecard",
            name="revoked_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.CreateModel(
            name="AppleRegistration",
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
                ("device", models.CharField(max_length=128)),
                ("push_token", models.CharField(max_length=256)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "card",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="apple_registrations",
                        to="idcard.employeecard",
                    ),
                ),
            ],
        ),
        migrations.AddConstraint(
            model_name="appleregistration",
            constraint=models.UniqueConstraint(
                fields=("card", "device"), name="idcard_appleregistration_unique"
            ),
        ),
    ]
