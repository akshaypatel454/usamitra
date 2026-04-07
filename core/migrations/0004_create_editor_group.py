from django.db import migrations


def create_editor_group(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Group.objects.get_or_create(name="Fund Editors")


class Migration(migrations.Migration):

    dependencies = [
        ("auth", "0012_alter_user_first_name_max_length"),
        ("core", "0003_sync_member_roster"),
    ]

    operations = [
        migrations.RunPython(create_editor_group, migrations.RunPython.noop),
    ]
