"""Clause: one piece of structured evidence extracted from a vendor
contract for a single policy-relevant clause type.
"""

from __future__ import annotations

from typing import Optional, Union

from pydantic import BaseModel, Field, model_validator

# A number (percentage, day count) or free text (e.g. data-ownership
# wording). Narrower than Any so a list/object can't sneak in as a value.
ClauseValue = Union[float, str]


class Clause(BaseModel):
    """One extracted fact about the vendor contract.

    Absent clauses use ``not_specified=True`` rather than a magic
    ``vendor_value`` string, so the value field stays typed and callers
    can check a flag instead of string-comparing. See the validator
    below for the None-fields invariant this implies.
    """

    clause_type: str = Field(
        description="Policy-relevant clause category, e.g. 'price_escalation'."
    )
    vendor_value: Optional[ClauseValue] = Field(
        default=None,
        description="Extracted value. None when not_specified is True.",
    )
    unit: Optional[str] = Field(
        default=None,
        description="Unit for vendor_value, e.g. 'percent', 'days'. Optional - a text clause has no unit.",
    )
    source_section: Optional[str] = Field(
        default=None,
        description="Contract section/clause reference, e.g. '4.2'. None when not_specified.",
    )
    source_text: Optional[str] = Field(
        default=None,
        description="Verbatim contract text the value was extracted from. None when not_specified.",
    )
    confidence: float = Field(
        ge=0.0, le=1.0, description="Extractor's confidence in this fact, 0-1."
    )
    not_specified: bool = Field(
        default=False,
        description="True if the vendor contract does not address this clause type at all.",
    )
    clause_id: Optional[str] = Field(
        default=None,
        description=(
            "Optional identifier (e.g. 'CL-014') bridging to the evidence "
            "store described in architecture.md. Lets NegotiationProposal "
            "and PolicyCheckResult reference this exact clause instead of "
            "free text. The harness may assign one if the extractor does not."
        ),
    )

    @model_validator(mode="after")
    def _check_not_specified_consistency(self) -> "Clause":
        if self.not_specified:
            if self.vendor_value is not None:
                raise ValueError("vendor_value must be None when not_specified=True")
        elif self.vendor_value is None:
            raise ValueError("vendor_value is required when not_specified=False")
        return self
