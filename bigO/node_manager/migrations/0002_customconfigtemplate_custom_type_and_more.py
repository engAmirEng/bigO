# Generated by Django 4.2.16 on 2024-10-29 17:04

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('node_manager', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='customconfigtemplate',
            name='custom_type',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='customtype_customconfigtemplates', to='node_manager.customprogramtype'),
        ),
        migrations.AddConstraint(
            model_name='customconfigtemplate',
            constraint=models.CheckConstraint(check=models.Q(models.Q(models.Q(('custom_type__isnull', False), ('type__isnull', True)), models.Q(('custom_type__isnull', True), ('type__isnull', False)), _connector='OR')), name='type_or_custom_type_config'),
        ),
    ]