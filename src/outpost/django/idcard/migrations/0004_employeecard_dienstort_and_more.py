from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('idcard', '0003_employeecard_email'),
    ]

    operations = [
        migrations.AddField(
            model_name='employeecard',
            name='title_prefix',
            field=models.CharField(blank=True, max_length=200),
        ),
        migrations.AddField(
            model_name='employeecard',
            name='title_suffix',
            field=models.CharField(blank=True, max_length=200),
        ),
        migrations.AddField(
            model_name='employeecard',
            name='organizational_unit_short',
            field=models.CharField(blank=True, help_text='OE short code (e.g. O-IT)', max_length=32),
        ),
        migrations.AddField(
            model_name='employeecard',
            name='dienstort',
            field=models.CharField(blank=True, help_text='Work address (Organization.address)', max_length=300),
        ),
        migrations.AddField(
            model_name='employeecard',
            name='organization_phone',
            field=models.CharField(blank=True, max_length=64),
        ),
        migrations.AddField(
            model_name='employeecard',
            name='organization_email',
            field=models.EmailField(blank=True, max_length=254),
        ),
    ]
