# Generated by Django 5.0.2 on 2024-10-03 13:20

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("c2c_modules", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="ProfilingResult",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("path", models.CharField(max_length=255)),
                ("function_name", models.CharField(max_length=255)),
                ("cumulative_time", models.FloatField()),
                ("timestamp", models.DateTimeField(auto_now_add=True)),
            ],
        ),
    ]
