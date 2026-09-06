"""Clause: one piece of structured evidence extracted from a vendor
contract for a single policy-relevant clause type.
"""

from __future__ import annotations

from typing import Optional, Union

from pydantic import BaseModel, Field, model_validator

# A clause's value can be a plain number (a percentage, a day count) or
# free text (e.g. a data-ownership clause's wording). Kept as a narrow
# union rather than Any so validation still rejects nonsense like a list
# or a nested object showing up where a scalar is expected.
ClauseValue = Union[float, str]


class Clause(BaseModel):
    """One extracted fact about the vendor contract.

    Design choice - representing an absent clause:
    A vendor contract that never addresses a policy-relevant clause type
    (for example, it says nothing about data ownership) is represented
    with ``not_specified=True``, a dedicated boolean flag, rather than a
    magic string such as ``vendor_value="NOT_SPECIFIED"``. Two reasons:

    1. ``vendor_value`` stays typed to the clause's real value (a number
       or free text). A sentinel string could collide with a legitimate
       text-valued clause that happens to contain that literal text.
    2. Callers can check ``if clause.not_specified`` directly instead of
       string-comparing a value field, which is what every downstream
       consumer (the policy engine, agents, the UI) actually wants to do.

    When ``not_specified`` is True there is no source passage to point
    to, so ``vendor_value``, ``unit``, ``source_section`` and
    ``source_text`` are all ``None`` - enforced by the validator below.
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
