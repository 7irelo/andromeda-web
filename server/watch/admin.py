from django.contrib import admin
from .models import Video, VideoComment

# If using Django admin with Neo4j, you'd typically have to register models with a different strategy.
# Here is a basic setup:

admin.site.register(Video)
admin.site.register(VideoComment)
