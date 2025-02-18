from pydantic import ValidationError as PydanticValidationError

from rest_framework.exceptions import ValidationError as DRFValidationError


def pydantic_to_drf_error(exc: PydanticValidationError) -> DRFValidationError:
    """
    Convert Pydantic ValidationError to Django REST Framework ValidationError.
    """
    error_dict = {}
    for error in exc.errors():
        loc = error.get("loc", [])
        field = loc[0] if loc else "non_field_errors"
        message = error.get("msg", "Invalid input")
        error_dict.setdefault(field, []).append(message)

    return DRFValidationError(detail=error_dict)
