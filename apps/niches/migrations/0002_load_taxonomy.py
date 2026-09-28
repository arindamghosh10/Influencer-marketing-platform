from django.db import migrations


def load(apps, schema_editor):
    from apps.niches.taxonomy import TAXONOMY

    Niche = apps.get_model("niches", "Niche")
    for i, (slug, name, keywords, children) in enumerate(TAXONOMY):
        parent, _ = Niche.objects.update_or_create(
            slug=slug, defaults={"name": name, "keywords": keywords, "sort_order": i}
        )
        for j, (child_slug, child_name, child_keywords) in enumerate(children):
            Niche.objects.update_or_create(
                slug=child_slug,
                defaults={
                    "name": child_name,
                    "keywords": child_keywords,
                    "parent": parent,
                    "sort_order": j,
                },
            )


class Migration(migrations.Migration):
    dependencies = [("niches", "0001_initial")]
    operations = [migrations.RunPython(load, migrations.RunPython.noop)]
