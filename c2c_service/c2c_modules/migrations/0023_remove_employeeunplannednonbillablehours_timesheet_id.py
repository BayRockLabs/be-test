# Generated by Django 5.0.2 on 2024-12-17 21:06

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('c2c_modules', '0022_employeeunplannednonbillablehours'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='employeeunplannednonbillablehours',
            name='timesheet_id',
        ),
    ]
