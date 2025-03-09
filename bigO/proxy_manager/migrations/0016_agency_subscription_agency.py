# Generated by Django 4.2.17 on 2025-03-09 14:38

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('proxy_manager', '0015_rename_consumers_obj_template_inbound_consumer_obj_template_and_more'),
    ]

    operations = [
        migrations.CreateModel(
            name='Agency',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('name', models.SlugField()),
                ('sublink_header_template', models.TextField(help_text='{{ subscription_obj }}', null=True)),
            ],
            options={
                'abstract': False,
            },
        ),
        migrations.AddField(
            model_name='subscription',
            name='agency',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.PROTECT, related_name='agency_subscriptions', to='proxy_manager.agency'),
        ),
    ]
