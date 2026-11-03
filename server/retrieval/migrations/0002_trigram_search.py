from django.db import migrations

# (app, model, fields): the text columns lexical search matches, see core/search.py.
TARGETS = [
    ('users', 'User', ['username', 'first_name', 'last_name']),
    ('posts', 'Post', ['content', 'link_title']),
    ('groups', 'Group', ['name', 'description']),
    ('pages', 'Page', ['name', 'description']),
    ('marketplace', 'Listing', ['title', 'description']),
    ('watch', 'Video', ['title', 'description']),
]


def create(apps, schema_editor):
    if schema_editor.connection.vendor != 'postgresql':
        return
    schema_editor.execute('CREATE EXTENSION IF NOT EXISTS pg_trgm')
    for app, model, fields in TARGETS:
        table = apps.get_model(app, model)._meta.db_table
        for field in fields:
            schema_editor.execute(
                f'CREATE INDEX IF NOT EXISTS "{table}_{field}_trgm" ON "{table}" USING gin ("{field}" gin_trgm_ops)')


def drop(apps, schema_editor):
    if schema_editor.connection.vendor != 'postgresql':
        return
    for app, model, fields in TARGETS:
        table = apps.get_model(app, model)._meta.db_table
        for field in fields:
            schema_editor.execute(f'DROP INDEX IF EXISTS "{table}_{field}_trgm"')


class Migration(migrations.Migration):
    dependencies = [
        ('retrieval', '0001_initial'),
        ('users', '__first__'),
        ('posts', '__first__'),
        ('groups', '__first__'),
        ('pages', '__first__'),
        ('marketplace', '__first__'),
        ('watch', '__first__'),
    ]

    operations = [migrations.RunPython(create, drop)]
