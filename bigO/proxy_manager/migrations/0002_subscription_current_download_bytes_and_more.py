# Generated by Django 4.2.17 on 2025-02-22 10:04

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('proxy_manager', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='subscription',
            name='current_download_bytes',
            field=models.PositiveBigIntegerField(default=0),
        ),
        migrations.AddField(
            model_name='subscription',
            name='current_upload_bytes',
            field=models.PositiveBigIntegerField(default=0),
        ),
    ]
