# Generated by Django 4.2.17 on 2025-03-06 15:44

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('node_manager', '0021_publicip_region'),
        ('proxy_manager', '0012_alter_connectionrule_xray_rules_template'),
    ]

    operations = [
        migrations.CreateModel(
            name='OutboundGroup',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('name', models.SlugField()),
            ],
            options={
                'abstract': False,
            },
        ),
        migrations.CreateModel(
            name='NodeOutbound',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('name', models.SlugField()),
                ('xray_outbound_template', models.TextField(help_text='{{ node }}')),
                ('group', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='group_nodeoutbounds', to='proxy_manager.outboundgroup')),
                ('node', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='node_nodeoutbounds', to='node_manager.node')),
            ],
            options={
                'abstract': False,
            },
        ),
    ]
