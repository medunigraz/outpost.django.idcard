from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("idcard", "0001_initial"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="employeecard",
            options={
                "ordering": ("-created_at",),
                "permissions": (
                    ("manage_passes", "Can download and re-push any employee's passes"),
                ),
                "verbose_name": "Employee ID card",
                "verbose_name_plural": "Employee ID cards",
            },
        ),
    ]
