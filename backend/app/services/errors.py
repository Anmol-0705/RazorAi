"""Service-layer errors, translated to HTTP responses at the API edge
(`app.api.routers`). Keeps HTTP status codes out of the service layer.
"""


class NotFoundError(Exception):
    pass


class ConflictError(Exception):
    pass
