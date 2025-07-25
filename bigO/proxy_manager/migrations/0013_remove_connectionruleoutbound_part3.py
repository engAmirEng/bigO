# Generated by Django 5.1.7 on 2025-06-01 10:30

import django.db.models.deletion
from django.db import migrations, models



class Migration(migrations.Migration):

    dependencies = [
        ("proxy_manager", "0012_remove_connectionruleoutbound_part2"),
    ]

    operations = [
        migrations.AddConstraint(
            model_name="nodeoutbound",
            constraint=models.UniqueConstraint(
                fields=("name", "node", "rule"), name="unique_name_node_rule_nodeoutbound"
            ),
        ),
        migrations.DeleteModel(
            name="ConnectionRuleOutbound",
        ),
        migrations.AlterField(
            model_name="nodeoutbound",
            name="balancer_allocation_str",
            field=models.CharField(help_text="balancertag1:weght,balancertag1:weght", max_length=255),
        ),
        migrations.AlterField(
            model_name="nodeoutbound",
            name="rule",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="rule_nodeoutbounds",
                to="proxy_manager.connectionrule",
            ),
        ),
    ]
