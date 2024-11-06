import re

from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.db import models


def validate_regex_pattern(value):
    try:
        re.compile(value)
    except re.error:
        raise ValidationError(f"Invalid regex pattern: '{value}'")


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class TextExtractor(TimeStampedModel, models.Model):
    name = models.CharField(max_length=255)
    regex_pattern = models.TextField(validators=[RegexValidator])

    def extract(self, raw_text: str):
        match = re.search(self.regex_pattern, raw_text, re.DOTALL)
        if match is not None:
            return match.group(1)
