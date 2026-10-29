"""Structural adapter from the binary equipment decision to legacy inspection fields."""

from .models import RentalInspection


class InspectionDecisionAdapter:
    OPERATING = "OPERATING"
    BROKEN = "BROKEN"

    @classmethod
    def to_inspection_fields(cls, decision):
        if decision == cls.OPERATING:
            return {
                "condition": RentalInspection.Condition.GOOD,
                "result": RentalInspection.Result.APPROVED,
                "critical_impediment": False,
            }
        if decision == cls.BROKEN:
            return {
                "condition": RentalInspection.Condition.DAMAGED,
                "result": RentalInspection.Result.BLOCKED,
                "critical_impediment": False,
            }
        raise ValueError("Decisão operacional desconhecida.")

    @classmethod
    def from_inspection(cls, inspection):
        if inspection.result == RentalInspection.Result.PENDING:
            return "PENDING"
        if inspection.result == RentalInspection.Result.BLOCKED or inspection.condition in {
            RentalInspection.Condition.DAMAGED, RentalInspection.Condition.CRITICAL,
        }:
            return cls.BROKEN
        return cls.OPERATING
