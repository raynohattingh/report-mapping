"""Schema loading + validation for onboarding artifacts (feature 003, FR-018).

Recipes, proposals, and PDF template configs are DATA validated against these
JSON Schemas before anything is registered (Constitution IV). The .json files
are the package-data copies of specs/003-pdf-format-onboarding/contracts/.
"""

from __future__ import annotations

import json
from importlib import resources

import jsonschema

_NAMES = {
    "recipe": "recipe.schema.json",
    "proposal": "proposal.schema.json",
    "pdf_template": "pdf-template.schema.json",
}


def load_schema(name: str) -> dict:
    """Return the parsed JSON Schema for 'recipe' | 'proposal' | 'pdf_template'."""
    fname = _NAMES[name]
    with resources.files(__package__).joinpath(fname).open("rb") as fh:
        return json.load(fh)


class SchemaValidationError(ValueError):
    """A document failed validation against its onboarding schema."""


def _validate(name: str, document: dict) -> dict:
    validator = jsonschema.Draft202012Validator(load_schema(name))
    errors = sorted(validator.iter_errors(document), key=lambda e: list(e.absolute_path))
    if errors:
        detail = "; ".join(
            f"{'/'.join(str(p) for p in e.absolute_path) or '<root>'}: {e.message}"
            for e in errors[:5]
        )
        raise SchemaValidationError(f"{name} document invalid: {detail}")
    return document


def validate_recipe(document: dict) -> dict:
    return _validate("recipe", document)


def validate_proposal(document: dict) -> dict:
    return _validate("proposal", document)


def validate_pdf_template(document: dict) -> dict:
    return _validate("pdf_template", document)
