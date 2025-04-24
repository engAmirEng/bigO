from io import BytesIO

from django.conf import settings
from django.core.exceptions import RequestDataTooBig
from django.http import HttpRequest, UnreadablePostError, RawPostDataException


def get_body_from_request(request: HttpRequest, max_body_size: int):
    if not hasattr(request, "_body"):
        if request._read_started:
            raise RawPostDataException(
                "You cannot access body after reading from request's data stream"
            )

        # Limit the maximum request data size that will be handled in-memory.
        if (
            settings.DATA_UPLOAD_MAX_MEMORY_SIZE is not None
            and int(request.META.get("CONTENT_LENGTH") or 0)
            > max_body_size
        ):
            raise RequestDataTooBig(
                "Request body exceeded settings.DATA_UPLOAD_MAX_MEMORY_SIZE."
            )

        try:
            request._body = request.read()
        except OSError as e:
            raise UnreadablePostError(*e.args) from e
        finally:
            request._stream.close()
        request._stream = BytesIO(request._body)
    return request._body
