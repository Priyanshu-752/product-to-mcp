class ProductToMcpError(RuntimeError):
    """Base error translated into a safe API response."""


class NotFoundError(ProductToMcpError):
    pass


class ValidationError(ProductToMcpError):
    pass


class UnsupportedError(ProductToMcpError):
    pass

