from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.pricing.config import PricingPolicy


class EligibilityError(ValueError):
    """Raised when an email cannot be normalized as an email address."""


@dataclass(frozen=True, slots=True)
class IdentityFacts:
    """Identity facts loaded by the server before pricing is evaluated."""

    email: str
    email_verified: bool = False
    identity_id: str | None = None


@dataclass(frozen=True, slots=True)
class EventFacts:
    """Event facts loaded by the server before pricing is evaluated."""

    event_id: str
    classification: str | None = None
    funding_source: str | None = None


@dataclass(frozen=True, slots=True)
class EligibilityDecision:
    """The privacy-minimized eligibility result captured in a quote."""

    eligible: bool
    reason: str
    normalized_email: str | None
    policy_revision: str


def normalize_email(email: str) -> str:
    """Trim and case-fold an email without applying provider-specific aliases."""

    if not isinstance(email, str):
        raise EligibilityError("email must be a string")
    if not email or any(ord(character) < 32 for character in email):
        raise EligibilityError("email contains a control character")

    value = email.strip()
    if not value or any(character.isspace() for character in value):
        raise EligibilityError("email contains invalid whitespace")
    if value.count("@") != 1:
        raise EligibilityError("email must contain exactly one @")

    local_part, domain = value.rsplit("@", 1)
    if not local_part or not domain or domain.startswith(".") or ".." in domain:
        raise EligibilityError("email has an invalid local part or domain")
    if "." not in domain:
        raise EligibilityError("email domain must contain a dot")

    return f"{local_part.casefold()}@{domain.casefold()}"


def evaluate_student_eligibility(
    identity_facts: IdentityFacts,
    event_facts: EventFacts,
    policy: PricingPolicy,
) -> EligibilityDecision:
    """Evaluate the configured local eligibility predicate without I/O."""

    if not isinstance(identity_facts, IdentityFacts):
        raise EligibilityError("identity facts must be server-owned IdentityFacts")
    if not isinstance(event_facts, EventFacts) or not event_facts.event_id.strip():
        raise EligibilityError("event facts must be server-owned EventFacts")
    if policy is None:
        raise EligibilityError("eligibility policy is required")

    policy_revision = policy.revision
    try:
        normalized = normalize_email(identity_facts.email)
    except EligibilityError:
        return EligibilityDecision(False, "invalid_email", None, policy_revision)

    local_part, domain = normalized.rsplit("@", 1)
    if not policy.allow_plus_addressing and "+" in local_part:
        return EligibilityDecision(False, "plus_address_not_allowed", normalized, policy_revision)
    if policy.allow_subdomains:
        domain_matches = domain == policy.eligibility_domain or domain.endswith(
            f".{policy.eligibility_domain}"
        )
    else:
        domain_matches = domain == policy.eligibility_domain
    if not domain_matches:
        return EligibilityDecision(False, "domain_not_eligible", normalized, policy_revision)
    if policy.require_verified_email and not identity_facts.email_verified:
        return EligibilityDecision(False, "email_not_verified", normalized, policy_revision)

    return EligibilityDecision(True, "eligible", normalized, policy_revision)


__all__ = [
    "EligibilityDecision",
    "EligibilityError",
    "EventFacts",
    "IdentityFacts",
    "evaluate_student_eligibility",
    "normalize_email",
]
