# Generated by Django 5.0.2 on 2025-01-20 18:48

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('c2c_modules', '0034_employeeentrytimesheet_date_created_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='employeeentrytimesheet',
            name='approved_by',
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
        migrations.AddField(
            model_name='employeeunplannednonbillablehours',
            name='approved_by',
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
    ]
