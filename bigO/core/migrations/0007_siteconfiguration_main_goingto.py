# Generated by Django 5.1.7 on 2025-05-01 15:37

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0006_big_migration_1"),
        ("node_manager", "0020_big_migration_1_2"),
    ]

    operations = [
        migrations.AddField(
            model_name="siteconfiguration",
            name="main_goingto",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="+",
                to="node_manager.programversion",
            ),
        ),
    ]
