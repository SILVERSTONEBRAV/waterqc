from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("alerts", "0005_voice_persistence_policy"),
    ]

    operations = [
        migrations.AlterField(
            model_name="alertstate",
            name="repeat_count",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AlterField(
            model_name="voicealert",
            name="repeat_count",
            field=models.PositiveIntegerField(default=0),
        ),
    ]
