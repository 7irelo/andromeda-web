from django.db import models
from pgvector.django import VectorField

DIMS = 1536  # text-embedding-3-small


class Embedding(models.Model):
    """
    One chunk of one piece of content, embedded for semantic search.

    Nothing about who may see the content is stored here. Every query joins
    against the viewer's visibility-filtered queryset inside the SQL, so a
    privacy change, block or deletion takes effect immediately without
    re-embedding or re-scoping anything.
    """

    kind = models.CharField(max_length=20)
    object_id = models.PositiveBigIntegerField()
    chunk_ix = models.PositiveSmallIntegerField(default=0)
    text = models.TextField()
    content_hash = models.CharField(max_length=64)
    vector = VectorField(dimensions=DIMS)
    model = models.CharField(max_length=60)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['kind', 'object_id', 'chunk_ix'], name='uniq_embedding_chunk')]
        indexes = [models.Index(fields=['kind', 'object_id'])]

    def __str__(self):
        return f'{self.kind}:{self.object_id}#{self.chunk_ix}'
