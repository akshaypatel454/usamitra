import django.db.models.deletion
import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0005_fundadjustment"),
    ]

    operations = [
        migrations.CreateModel(
            name="MemberInterestPayout",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("payout_date", models.DateField(default=django.utils.timezone.localdate)),
                ("amount", models.DecimalField(decimal_places=2, max_digits=12)),
                ("notes", models.TextField(blank=True)),
                ("member", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="interest_payouts", to="core.member")),
            ],
            options={
                "ordering": ["-payout_date", "member__full_name", "-id"],
            },
        ),
    ]
