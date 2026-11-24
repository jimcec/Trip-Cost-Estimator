"""Core validation and calculation logic for the Trip Cost Estimate microservice.

Implements CS361 Sprint 3 Plan — Microservice 8: Trip Cost Estimate.
Uses Decimal arithmetic with ROUND_HALF_UP so every monetary value is rounded
to the nearest cent and total_cost strictly equals the sum of the returned
itemized components.
"""

from __future__ import annotations

import json
import math
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any

CENT = Decimal("0.01")


class ValidationError(ValueError):
    """Raised when a trip cost request fails input validation."""

    def __init__(self, message: str, field: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.field = field


def _round_cents(value: Decimal) -> Decimal:
    """Round a Decimal monetary value to the nearest cent."""
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def _parse_number(value: Any, field_name: str) -> Decimal:
    """Validate and convert a JSON numeric value to a finite Decimal."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValidationError(
            f"Invalid input for '{field_name}': expected a numeric value.",
            field=field_name,
        )
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        raise ValidationError(
            f"Invalid input for '{field_name}': value must be a finite number.",
            field=field_name,
        )
    try:
        return Decimal(str(value))
    except InvalidOperation as exc:
        raise ValidationError(
            f"Invalid input for '{field_name}': could not parse numeric value.",
            field=field_name,
        ) from exc


def _parse_required_field(payload: dict[str, Any], field_name: str) -> Decimal:
    """Extract and parse a required numeric field from the request payload."""
    if field_name not in payload or payload[field_name] is None:
        raise ValidationError(
            f"Missing required input: '{field_name}'.",
            field=field_name,
        )
    return _parse_number(payload[field_name], field_name)


def _parse_optional_fee(payload: dict[str, Any], field_name: str) -> Decimal:
    """Extract and parse an optional fee field, defaulting omitted/null to 0.00."""
    if field_name not in payload or payload[field_name] is None:
        return Decimal("0.00")
    fee = _parse_number(payload[field_name], field_name)
    if fee < 0:
        raise ValidationError(
            f"Invalid fee '{field_name}': must be zero or greater.",
            field=field_name,
        )
    return _round_cents(fee)


def calculate_trip_cost(payload: dict[str, Any]) -> dict[str, Any]:
    """Validate inputs and compute itemized fuel cost, fees, and total trip cost.

    Args:
        payload: Request dictionary containing:
            - distance (float | int): Total trip distance in miles (>= 0).
            - fuel_efficiency (float | int): Vehicle fuel efficiency in MPG (> 0).
            - fuel_price (float | int): Fuel price per gallon in USD (>= 0).
            - parking_fee (float | int, optional): Parking fee in USD (>= 0).
            - entrance_fee (float | int, optional): Entrance fee in USD (>= 0).

    Returns:
        Dictionary with status "ok" and rounded monetary values:
        fuel_cost, parking_fee, entrance_fee, and total_cost.

    Raises:
        ValidationError: If any input is missing, non-numeric, or out of range.
    """
    if not isinstance(payload, dict):
        raise ValidationError("Invalid request: JSON payload must be an object.")

    distance = _parse_required_field(payload, "distance")
    fuel_efficiency = _parse_required_field(payload, "fuel_efficiency")
    fuel_price = _parse_required_field(payload, "fuel_price")

    if distance < 0:
        raise ValidationError(
            "Invalid input for 'distance': distance cannot be negative.",
            field="distance",
        )
    if fuel_efficiency <= 0:
        raise ValidationError(
            "Invalid input for 'fuel_efficiency': fuel efficiency must be greater than zero.",
            field="fuel_efficiency",
        )
    if fuel_price < 0:
        raise ValidationError(
            "Invalid input for 'fuel_price': fuel price cannot be negative.",
            field="fuel_price",
        )

    parking_fee = _parse_optional_fee(payload, "parking_fee")
    entrance_fee = _parse_optional_fee(payload, "entrance_fee")

    if distance == 0:
        fuel_cost = Decimal("0.00")
    else:
        fuel_cost = _round_cents((distance / fuel_efficiency) * fuel_price)

    total_cost = _round_cents(fuel_cost + parking_fee + entrance_fee)

    return {
        "status": "ok",
        "fuel_cost": float(fuel_cost),
        "parking_fee": float(parking_fee),
        "entrance_fee": float(entrance_fee),
        "total_cost": float(total_cost),
    }


def handle_request(payload: Any) -> dict[str, Any]:
    """Process a decoded JSON payload and return a response dict (never raises)."""
    try:
        return calculate_trip_cost(payload)
    except ValidationError as exc:
        response: dict[str, Any] = {
            "status": "error",
            "error": exc.message,
        }
        if exc.field is not None:
            response["field"] = exc.field
        return response


def handle_raw_message(raw_message: bytes | str) -> bytes:
    """Decode a raw JSON message, process it, and return UTF-8 JSON bytes."""
    try:
        text = (
            raw_message.decode("utf-8")
            if isinstance(raw_message, bytes)
            else raw_message
        )
        payload = json.loads(text)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        error_response = {
            "status": "error",
            "error": f"Invalid JSON request: {exc}",
        }
        return json.dumps(error_response).encode("utf-8")

    response = handle_request(payload)
    return json.dumps(response).encode("utf-8")
