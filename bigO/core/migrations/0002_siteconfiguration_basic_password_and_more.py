# Generated by Django 4.2.17 on 2025-01-14 15:23

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('node_manager', '0012_nodesupervisorconfig'),
        ('core', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='siteconfiguration',
            name='basic_password',
            field=models.CharField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='siteconfiguration',
            name='basic_username',
            field=models.CharField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='siteconfiguration',
            name='htpasswd_content',
            field=models.TextField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='siteconfiguration',
            name='main_nginx',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.PROTECT, to='node_manager.programversion'),
        ),
    ]
