# Generated by Django 5.1.7 on 2025-05-15 14:53

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("proxy_manager", "0007_alter_nodeoutbound_xray_outbound_template_and_more"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="nodeoutbound",
            name="group",
        ),
        migrations.AlterModelOptions(
            name="internaluser",
            options={"ordering": ["-created_at"]},
        ),
        migrations.AddField(
            model_name="internaluser",
            name="first_usage_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="internaluser",
            name="last_usage_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="nodeoutbound",
            name="to_inbound_type",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="toinboundtype_nodeoutbounds",
                to="proxy_manager.inboundtype",
            ),
        ),
        migrations.CreateModel(
            name="ConnectionRuleOutbound",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("name", models.CharField()),
                (
                    "node_outbound",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="nodeoutbound_connectionruleoutbounds",
                        to="proxy_manager.nodeoutbound",
                    ),
                ),
                (
                    "rule",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="rule_connectionruleoutbounds",
                        to="proxy_manager.connectionrule",
                    ),
                ),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
        migrations.DeleteModel(
            name="OutboundGroup",
        ),
    ]
