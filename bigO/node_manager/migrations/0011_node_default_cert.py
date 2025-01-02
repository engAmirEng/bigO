# Generated by Django 4.2.17 on 2025-01-02 15:18

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0001_initial'),
        ('node_manager', '0010_customconfig_customconfigdependantfile_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='node',
            name='default_cert',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='core.certificate'),
        ),
    ]
