import json
import uuid

from bilbyui.models import AnonymousMetrics


class AnonymousMetricsMiddleware(object):
    def resolve(self, next, root, info, **args):
        # If the tracking headers are not passed through, or the user is authenticated, then there is nothing more to
        # do. Also ignore any paths that aren't the top level (ie, nodes and fields)
        if 'X-Correlation-ID' not in info.context.headers or info.context.user.is_authenticated or len(info.path) > 1:
            return next(root, info, **args)

        # Get the tracking header and split it by space to get the persistent and session ids
        header = info.context.headers['X-Correlation-ID']

        # Check that a space exists in the header to separate the ids
        if ' ' not in header:
            return next(root, info, **args)

        # Check that there is exactly two ids
        ids = header.split(' ')
        if len(ids) != 2:
            return next(root, info, **args)

        # Check that the two ids are valid uuid4's
        try:
            ids[0] = uuid.UUID(ids[0])
            ids[1] = uuid.UUID(ids[1])
        except ValueError:
            return next(root, info, **args)

        # Details of the request are valid, we can create the metrics entry
        AnonymousMetrics.objects.create(
            public_id=ids[0],
            session_id=ids[1],
            request=info.path[0],   # We only care about the top level object type being requested
            params=json.dumps(args)
        )

        # Continue the request
        return next(root, info, **args)
