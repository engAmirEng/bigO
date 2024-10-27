# Generated by Django 4.2.16 on 2024-10-27 19:32

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('node_manager', '0002_easytiernode_ipv4'),
    ]

    operations = [
        migrations.AddConstraint(
            model_name='easytiernodepeer',
            constraint=models.UniqueConstraint(fields=('node', 'peer_listener', 'peer_public_ip'), name='unique_peer_listener_peer_public_ip_per_node'),
        ),
    ]
