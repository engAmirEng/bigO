# Generated by Django 4.2.16 on 2024-11-07 17:14

import django.core.validators
from django.db import migrations, models
import django.db.models.deletion
import netfields.fields


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('utils', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='ContainerSpec',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('ipv4', netfields.fields.InetAddressField(blank=True, help_text='the internal ip that is constantly changed, this is a stational entity', max_length=39, null=True, validators=[django.core.validators.validate_ipv4_address])),
                ('ipv6', netfields.fields.InetAddressField(blank=True, help_text='the internal ip that is constantly changed, this is a stational entity', max_length=39, null=True, validators=[django.core.validators.validate_ipv6_address])),
                ('ip_a_container_ipv4_extractor', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='ipacontaineripv4extractor_containerspecs', to='utils.textextractor')),
                ('ip_a_container_ipv6_extractor', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='ipacontaineripv6extractor_containerspecs', to='utils.textextractor')),
            ],
            options={
                'abstract': False,
            },
        ),
        migrations.CreateModel(
            name='CustomConfigTemplate',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('name', models.CharField(max_length=255)),
                ('template', models.TextField(blank=True, help_text='{node_obj}', null=True)),
                ('run_opts_template', models.TextField(help_text='{node_obj, configfile_path_placeholder}')),
            ],
            options={
                'abstract': False,
            },
        ),
        migrations.CreateModel(
            name='EasyTierNetwork',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('network_name', models.CharField(max_length=255, unique=True)),
                ('network_secret', models.CharField(max_length=255)),
                ('ip_range', netfields.fields.CidrAddressField(max_length=43)),
            ],
            options={
                'abstract': False,
            },
        ),
        migrations.CreateModel(
            name='EasyTierNode',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('external_node', models.CharField(blank=True, help_text='tcp://public.easytier.top:11010', max_length=255, null=True)),
                ('ipv4', netfields.fields.InetAddressField(blank=True, help_text='this is a stational entity', max_length=39, null=True)),
                ('custom_toml_config_template', models.TextField(blank=True, null=True)),
                ('custom_run_opts_template', models.TextField(blank=True, null=True)),
                ('network', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='network_easytiernodes', to='node_manager.easytiernetwork')),
            ],
            options={
                'abstract': False,
            },
        ),
        migrations.CreateModel(
            name='EasyTierNodeListener',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('protocol', models.CharField(choices=[('tcp', 'Tcp'), ('udp', 'Udp'), ('ws', 'Ws'), ('wss', 'Wss')], max_length=15)),
                ('port', models.PositiveSmallIntegerField()),
                ('node', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='node_nodelisteners', to='node_manager.easytiernode')),
            ],
            options={
                'abstract': False,
            },
        ),
        migrations.CreateModel(
            name='Node',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('name', models.CharField(max_length=255)),
                ('is_tunable', models.BooleanField(default=True, help_text='can tuns be created on it?')),
                ('architecture', models.CharField(choices=[('amd64', 'Amd64')], max_length=63)),
                ('container_spec', models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='containerspec_nodes', to='node_manager.containerspec')),
            ],
            options={
                'abstract': False,
            },
        ),
        migrations.CreateModel(
            name='Program',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('name', models.CharField(max_length=127, unique=True)),
            ],
            options={
                'abstract': False,
            },
        ),
        migrations.CreateModel(
            name='PublicIP',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('name', models.CharField(blank=True, max_length=255, null=True)),
                ('ip', netfields.fields.InetAddressField(max_length=39, unique=True)),
                ('is_cdn', models.BooleanField(default=False)),
            ],
            options={
                'abstract': False,
            },
        ),
        migrations.CreateModel(
            name='ProgramVersion',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('version', models.CharField(max_length=63)),
                ('program', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='program_programversion', to='node_manager.program')),
            ],
        ),
        migrations.CreateModel(
            name='ProgramBinary',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('architecture', models.CharField(choices=[('amd64', 'Amd64')], max_length=63)),
                ('file', models.FileField(upload_to='protected/')),
                ('hash', models.CharField(db_index=True, max_length=64)),
                ('program_version', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='programversion_programbinaries', to='node_manager.programversion')),
            ],
        ),
        migrations.CreateModel(
            name='NodePublicIP',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('ip', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='ip_nodepublicips', to='node_manager.publicip')),
                ('node', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='node_nodepublicips', to='node_manager.node')),
            ],
        ),
        migrations.CreateModel(
            name='NodeInnerProgram',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('path', models.CharField(blank=True, max_length=255, null=True)),
                ('node', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='node_nodeinnerbinary', to='node_manager.node')),
                ('program_version', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='programversion_nodeinnerprograms', to='node_manager.programversion')),
            ],
        ),
        migrations.CreateModel(
            name='NodeCustomConfigTemplate',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('config_template', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='nodecustomconfigtemplates', to='node_manager.customconfigtemplate')),
                ('node', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='node_customconfigtemplates', to='node_manager.node')),
            ],
        ),
        migrations.CreateModel(
            name='NodeAPIKey',
            fields=[
                ('id', models.CharField(editable=False, max_length=150, primary_key=True, serialize=False, unique=True)),
                ('prefix', models.CharField(editable=False, max_length=8, unique=True)),
                ('hashed_key', models.CharField(editable=False, max_length=150)),
                ('created', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('name', models.CharField(default=None, help_text='A free-form name for the API key. Need not be unique. 50 characters max.', max_length=50)),
                ('revoked', models.BooleanField(blank=True, default=False, help_text='If the API key is revoked, clients cannot use it anymore. (This cannot be undone.)')),
                ('expiry_date', models.DateTimeField(blank=True, help_text='Once API key expires, clients cannot use it anymore.', null=True, verbose_name='Expires')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('node', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='apikeys', to='node_manager.node')),
            ],
            options={
                'abstract': False,
            },
        ),
        migrations.CreateModel(
            name='GostClientNode',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('node', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='gostservers', to='node_manager.node')),
            ],
            options={
                'abstract': False,
            },
        ),
        migrations.CreateModel(
            name='EasyTierNodePeer',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('node', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='node_nodepeers', to='node_manager.easytiernode')),
                ('peer_listener', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='peerlistener_nodepeers', to='node_manager.easytiernodelistener')),
                ('peer_public_ip', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='peerpublicip_nodepeers', to='node_manager.nodepublicip')),
            ],
        ),
        migrations.AddField(
            model_name='easytiernode',
            name='node',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='node_easytiernods', to='node_manager.node'),
        ),
        migrations.AddField(
            model_name='easytiernetwork',
            name='program_version',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='programversion_easytiernetworks', to='node_manager.programversion'),
        ),
        migrations.AddField(
            model_name='customconfigtemplate',
            name='program_version',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='programversion_customconfigtemplates', to='node_manager.programversion'),
        ),
        migrations.AddConstraint(
            model_name='programversion',
            constraint=models.UniqueConstraint(fields=('program', 'version'), name='unique_program_version'),
        ),
        migrations.AddConstraint(
            model_name='programbinary',
            constraint=models.UniqueConstraint(fields=('architecture', 'program_version'), name='unique_architecture_programversion'),
        ),
        migrations.AddConstraint(
            model_name='nodepublicip',
            constraint=models.UniqueConstraint(fields=('ip', 'node'), name='unique_node_ip'),
        ),
        migrations.AddConstraint(
            model_name='nodeinnerprogram',
            constraint=models.UniqueConstraint(fields=('path', 'node'), name='node_path_taken', violation_error_message='this path is already taken on the node.'),
        ),
        migrations.AddConstraint(
            model_name='nodeinnerprogram',
            constraint=models.UniqueConstraint(fields=('program_version', 'node'), name='innerprogram_unique_programversion_node', violation_error_message='this kind of program is already defined for this node node.'),
        ),
        migrations.AddConstraint(
            model_name='nodecustomconfigtemplate',
            constraint=models.UniqueConstraint(fields=('node', 'config_template'), name='unique_node_config_template'),
        ),
        migrations.AddConstraint(
            model_name='easytiernodepeer',
            constraint=models.UniqueConstraint(fields=('node', 'peer_listener', 'peer_public_ip'), name='unique_peer_listener_peer_public_ip_per_node'),
        ),
    ]
