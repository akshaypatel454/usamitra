import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0004_create_editor_group"),
    ]

    operations = [
        migrations.CreateModel(
            name="FundAdjustment",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("adjustment_date", models.DateField(default=django.utils.timezone.localdate)),
                ("amount", models.DecimalField(decimal_places=2, max_digits=12)),
                ("notes", models.TextField(blank=True)),
            ],
            options={
                "ordering": ["adjustment_date", "id"],
            },
        ),
    ]
