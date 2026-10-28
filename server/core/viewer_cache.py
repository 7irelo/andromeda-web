"""
Per-response memo for "what does the viewer have to do with this row?" lookups.

List serializers used to ask, for every row, "is the viewer a member / a
follower / a friend / has the viewer liked it?", one query per row and field.
Instead each such fact is loaded once per response, as a set or dict keyed by
row id, and kept in the serializer context, which DRF shares between a root
serializer and every nested one. A context lives for one response, so nothing
here outlives the request.
"""


def memo(serializer, key, loader):
    context = serializer.context
    store = context.setdefault('_viewer_cache', {}) if isinstance(context, dict) else {}
    if key not in store:
        store[key] = loader()
    return store[key]


def viewer(serializer):
    request = serializer.context.get('request') if isinstance(serializer.context, dict) else None
    user = getattr(request, 'user', None)
    return user if user is not None and user.is_authenticated else None


def relations(serializer):
    """The viewer's ``core.visibility.ViewerRelations``, shared across the response."""
    from core.visibility import ViewerRelations

    user = viewer(serializer)
    if user is None:
        return None
    return memo(serializer, ('relations', user.id), lambda: ViewerRelations(user))
