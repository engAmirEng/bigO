# Generated by Django 5.1.7 on 2025-05-24 08:43

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("node_manager", "0022_supervisorprocessinfo"),
    ]

    operations = [
        migrations.AlterField(
            model_name="supervisorprocessinfo",
            name="pid",
            field=models.PositiveBigIntegerField(blank=True, null=True),
        ),
    ]
