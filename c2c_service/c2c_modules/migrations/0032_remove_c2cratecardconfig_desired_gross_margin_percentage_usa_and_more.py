# Generated by Django 5.0.2 on 2025-01-17 17:48

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('c2c_modules', '0031_c2cratecardconfig_desired_gross_margin_percentage_usa_and_more'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='c2cratecardconfig',
            name='desired_gross_margin_percentage_usa',
        ),
        migrations.RemoveField(
            model_name='c2cratecardconfig',
            name='non_billable_days_per_year_usa',
        ),
        migrations.RemoveField(
            model_name='c2cratecardconfig',
            name='overhead_percentage_usa',
        ),
    ]
