from django.db import migrations

# Top-level categories and their children: (slug, name, icon, [(slug, name), ...]).
TREE = [
    ('electronics', 'Electronics', 'devices', [
        ('phones', 'Phones & Tablets'), ('computers', 'Computers & Laptops'), ('tv-audio', 'TV & Audio'),
        ('cameras', 'Cameras'), ('gaming', 'Gaming'),
    ]),
    ('home-garden', 'Home & Garden', 'chair', [
        ('furniture', 'Furniture'), ('appliances', 'Appliances'), ('kitchen', 'Kitchen & Dining'),
        ('garden', 'Garden & Outdoor'), ('decor', 'Decor'),
    ]),
    ('fashion', 'Clothing & Accessories', 'checkroom', [
        ('womens-fashion', "Women's Clothing"), ('mens-fashion', "Men's Clothing"), ('shoes', 'Shoes'),
        ('jewellery', 'Jewellery & Watches'),
    ]),
    ('vehicles', 'Vehicles', 'directions_car', [
        ('cars', 'Cars'), ('motorcycles', 'Motorcycles'), ('vehicle-parts', 'Parts & Accessories'),
    ]),
    ('sport', 'Sport & Leisure', 'sports_soccer', [
        ('bicycles', 'Bicycles'), ('fitness', 'Fitness'), ('camping', 'Camping & Hiking'),
    ]),
    ('baby-kids', 'Baby & Kids', 'child_friendly', [('toys', 'Toys'), ('baby-gear', 'Baby Gear')]),
    ('hobbies', 'Books, Music & Hobbies', 'menu_book', [
        ('books', 'Books'), ('instruments', 'Musical Instruments'), ('collectibles', 'Collectibles'),
    ]),
    ('tools-diy', 'Tools & DIY', 'handyman', []),
    ('pets', 'Pet Supplies', 'pets', []),
    ('other', 'Other', 'category', []),
]


def create_tree(apps, schema_editor):
    Category = apps.get_model('marketplace', 'Category')
    for slug, name, icon, children in TREE:
        parent, _ = Category.objects.get_or_create(slug=slug, defaults={'name': name, 'icon': icon})
        for child_slug, child_name in children:
            child, created = Category.objects.get_or_create(
                slug=child_slug, defaults={'name': child_name, 'parent': parent})
            if not created and child.parent_id is None:
                # Adopt categories created earlier (e.g. by the seeder) into the tree.
                child.parent = parent
                child.save(update_fields=['parent'])


class Migration(migrations.Migration):

    dependencies = [
        ('marketplace', '0004_listing_reserved_geo'),
    ]

    operations = [
        migrations.RunPython(create_tree, migrations.RunPython.noop),
    ]
