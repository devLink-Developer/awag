class GatewayError(Exception):
    def __init__(self, code: str, status_code: int = 422, retryable: bool = False):
        super().__init__(code)
        self.code = code
        self.status_code = status_code
        self.retryable = retryable
