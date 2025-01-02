# Generated by Django 4.2.17 on 2025-01-02 15:18

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('contenttypes', '0002_remove_content_type_name'),
    ]

    operations = [
        migrations.CreateModel(
            name='Certificate',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('slug', models.SlugField(unique=True)),
                ('algorithm', models.PositiveSmallIntegerField(verbose_name=[(1, 'RSA'), (2, 'ECDSA')])),
                ('content', models.TextField()),
                ('is_ca', models.BooleanField(default=False)),
                ('fingerprint', models.CharField(db_index=True, max_length=64)),
                ('valid_from', models.DateTimeField()),
                ('valid_to', models.DateTimeField()),
                ('parent_certificate', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, to='core.certificate')),
                ('polymorphic_ctype', models.ForeignKey(editable=False, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='polymorphic_%(app_label)s.%(class)s_set+', to='contenttypes.contenttype')),
            ],
        ),
        migrations.CreateModel(
            name='PrivateKey',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('slug', models.SlugField(unique=True)),
                ('algorithm', models.PositiveSmallIntegerField(verbose_name=[(1, 'RSA'), (2, 'ECDSA')])),
                ('content', models.TextField()),
                ('passphrase', models.CharField(blank=True, max_length=255, null=True)),
                ('key_length', models.PositiveSmallIntegerField()),
            ],
            options={
                'abstract': False,
            },
        ),
        migrations.CreateModel(
            name='SiteConfiguration',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('nodes_ca_cert', models.ForeignKey(null=True, on_delete=django.db.models.deletion.PROTECT, to='core.certificate')),
            ],
            options={
                'abstract': False,
            },
        ),
        migrations.AddField(
            model_name='certificate',
            name='private_key',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, to='core.privatekey'),
        ),
        migrations.AddConstraint(
            model_name='certificate',
            constraint=models.CheckConstraint(check=models.Q(models.Q(('is_ca', False), ('parent_certificate__isnull', True), _connector='OR')), name='isca_or_parentcertificate', violation_error_message='ca cert cannot have any parent cert'),
        ),
    ]
