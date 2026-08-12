from enum import StrEnum


class TravelType(StrEnum):
    FLIGHT = "flight"
    HOTEL = "hotel"


class RefreshType(StrEnum):
    CALENDAR_MONTH = "calendar_month"
    STATEMENT_DATE = "statement_date"


class PurchaseForm(StrEnum):
    VOUCHER = "voucher"
    PORTAL = "portal"
    CONCIERGE = "concierge"

