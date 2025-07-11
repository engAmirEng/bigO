# Generated by Django 5.1.7 on 2025-06-01 10:30
import django.db.models.deletion
from django.db import migrations, models



def perform(apps, schema_editor):
    NodeOutbound = apps.get_model('proxy_manager', 'NodeOutbound')
    ConnectionRuleOutbound = apps.get_model('proxy_manager', 'ConnectionRuleOutbound')

    for connectionruleoutbound in ConnectionRuleOutbound.objects.all():
        nodeoutbound = connectionruleoutbound.node_outbound
        nodeoutbound.id = None
        nodeoutbound.rule = connectionruleoutbound.rule
        nodeoutbound.name = nodeoutbound.name + str(connectionruleoutbound.id)
        nodeoutbound.balancer_allocation_str = f"{connectionruleoutbound.name}:1"
        nodeoutbound.save()

    ConnectionRuleOutbound.objects.all().delete()
    NodeOutbound.objects.filter(rule__isnull=True, balancer_allocation_str__isnull=True).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("proxy_manager", "0011_remove_connectionruleoutbound_part1"),
    ]

    operations = [
        migrations.RunPython(perform),
    ]
