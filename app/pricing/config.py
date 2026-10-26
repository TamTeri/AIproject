from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal

LOCAL_ONLY_LABEL = "PROVISIONAL_LOCAL_ONLY"
# "test" is disposable like local/development (same rule as database reset).
_LOCAL_ENVIRONMENTS = frozenset({"local", "development", "test"})


# !!! [TEMPORARY_MVP_DEFAULT] NOT APPROVED BY THE CUSTOMER — see Call 4 !!!
STUDENT_DISCOUNT_PERCENT_PLACEHOLDER = Decimal("10")


class PricingUnavailable(RuntimeError):
    """Raised when pricing cannot safely be made available."""


class PricingConfigurationError(PricingUnavailable, ValueError):
    """Raised when a pricing policy is missing or invalid."""


def _decimal_value(value: object, *, field: str) -> Decimal:
    if isinstance(value, bool) or isinstance(value, float):
        raise PricingConfigurationError(f"{field} must be an exact Decimal or string")
    if isinstance(value, Decimal):
        result = value
    elif isinstance(value, (str, int)):
        try:
            result = Decimal(str(value))
        except Exception as exc:  # pragma: no cover - Decimal's concrete errors vary
            raise PricingConfigurationError(f"{field} must be a valid Decimal") from exc
    else:
        raise PricingConfigurationError(f"{field} must be an exact Decimal or string")
    if not result.is_finite():
        raise PricingConfigurationError(f"{field} must be finite")
    return result


@dataclass(frozen=True, slots=True)
class PricingPolicy:
    """Explicit, versioned pricing inputs; no production policy is implied."""

    revision: str
    discount_percent: Decimal | str | int
    eligibility_domain: str
    currency_code: str = "USD"
    currency_exponent: int = 2
    discount_order: str = "discount_then_convert"
    rounding_mode: str = "ROUND_HALF_UP"
    rate_direction: str = "base_to_target"
    local_only: bool = True
    label: str = LOCAL_ONLY_LABEL
    allow_plus_addressing: bool = False
    allow_subdomains: bool = False
    require_verified_email: bool = False

    def __post_init__(self) -> None:
        revision = self.revision.strip() if isinstance(self.revision, str) else ""
        if not revision:
            raise PricingConfigurationError("policy revision is required")
        object.__setattr__(self, "revision", revision)

        discount_percent = _decimal_value(self.discount_percent, field="discount_percent")
        if discount_percent < 0 or discount_percent > 100:
            raise PricingConfigurationError("discount_percent must be between 0 and 100")
        if abs(discount_percent.as_tuple().exponent) > 4:
            raise PricingConfigurationError("discount_percent has excessive precision")
        object.__setattr__(self, "discount_percent", discount_percent)

        if not isinstance(self.eligibility_domain, str):
            raise PricingConfigurationError("eligibility_domain is required")
        domain = self.eligibility_domain.strip().casefold()
        if not domain or "@" in domain or any(character.isspace() for character in domain):
            raise PricingConfigurationError("eligibility_domain is invalid")
        object.__setattr__(self, "eligibility_domain", domain)

        # currency_code is the BASE currency event prices are stored in. Buyers
        # may pay in any enabled currency via configured exchange rates.
        currency_code = self.currency_code.strip().upper()
        if currency_code != "USD":
            raise PricingConfigurationError("USD is the only supported base currency")
        object.__setattr__(self, "currency_code", currency_code)
        if self.currency_exponent != 2:
            raise PricingConfigurationError("USD must use a two-digit minor unit exponent")
        if self.discount_order != "discount_then_convert":
            raise PricingConfigurationError("unsupported discount order")
        if self.rounding_mode != "ROUND_HALF_UP":
            raise PricingConfigurationError("unsupported rounding mode")
        if self.rate_direction != "base_to_target":
            raise PricingConfigurationError("unsupported rate direction")
        if not isinstance(self.label, str) or not self.label.strip():
            raise PricingConfigurationError("policy label is required")

    def validate_for_environment(self, environment: str) -> None:
        normalized_environment = environment.strip().casefold()
        if normalized_environment not in _LOCAL_ENVIRONMENTS or not self.local_only:
            raise PricingUnavailable("pricing policy is local-only; non-local environments fail closed")
        if LOCAL_ONLY_LABEL not in self.label:
            raise PricingUnavailable("local pricing policy must carry the provisional label")


def temporary_local_policy() -> PricingPolicy:
    """Return the explicitly requested local/demo policy, never a production default."""

    return PricingPolicy(
        revision="temporary-local-v1",
        # !!! [TEMPORARY_MVP_DEFAULT] NOT APPROVED BY THE CUSTOMER !!!
        # Call 4: the student-discount percentage is still not written down.
        # 10 is a flagged placeholder, not a decision. Change it here only.
        discount_percent=STUDENT_DISCOUNT_PERCENT_PLACEHOLDER,
        eligibility_domain="usf.edu",
        currency_code="USD",
        currency_exponent=2,
        discount_order="discount_then_convert",
        rounding_mode="ROUND_HALF_UP",
        rate_direction="base_to_target",
        local_only=True,
        label=LOCAL_ONLY_LABEL,
        allow_plus_addressing=False,
        allow_subdomains=False,
        require_verified_email=False,
    )


def policy_from_mapping(
    values: Mapping[str, object] | None,
    *,
    environment: str,
    local_opt_in: bool = False,
) -> PricingPolicy:
    """Load only explicit policy fields and reject missing or non-local configuration."""

    if not values:
        raise PricingUnavailable("pricing policy is required; no fallback is available")
    if environment.strip().casefold() not in _LOCAL_ENVIRONMENTS or not local_opt_in:
        raise PricingUnavailable("temporary pricing configuration requires explicit local opt-in")

    required = {
        "revision",
        "discount_percent",
        "eligibility_domain",
        "currency_code",
        "currency_exponent",
        "discount_order",
        "rounding_mode",
        "rate_direction",
        "local_only",
        "label",
    }
    missing = sorted(key for key in required if key not in values)
    if missing:
        raise PricingUnavailable(f"pricing policy is incomplete: missing {', '.join(missing)}")

    policy = PricingPolicy(
        revision=values["revision"],
        discount_percent=values["discount_percent"],
        eligibility_domain=values["eligibility_domain"],
        currency_code=values["currency_code"],
        currency_exponent=values["currency_exponent"],
        discount_order=values["discount_order"],
        rounding_mode=values["rounding_mode"],
        rate_direction=values["rate_direction"],
        local_only=values["local_only"],
        label=values["label"],
        allow_plus_addressing=values.get("allow_plus_addressing", False),
        allow_subdomains=values.get("allow_subdomains", False),
        require_verified_email=values.get("require_verified_email", False),
    )
    policy.validate_for_environment(environment)
    return policy


__all__ = [
    "LOCAL_ONLY_LABEL",
    "STUDENT_DISCOUNT_PERCENT_PLACEHOLDER",
    "PricingConfigurationError",
    "PricingPolicy",
    "PricingUnavailable",
    "policy_from_mapping",
    "temporary_local_policy",
]
