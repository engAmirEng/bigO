# Generated by Django 4.2.17 on 2025-02-22 17:45

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('proxy_manager', '0004_config_nginx_config_template_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='inbound',
            name='nginx_path_config',
            field=models.TextField(default='#fdfd'),
            preserve_default=False,
        ),
    ]
