import enum


class UserRole(str, enum.Enum):
    rider = "rider"
    driver = "driver"


class OTPPurpose(str, enum.Enum):
    login = "login"
    register = "register"


class CreditTransactionType(str, enum.Enum):
    email_bonus = "email_bonus"
    promo = "promo"
    referral = "referral"
    ride_applied = "ride_applied"


class RideStatus(str, enum.Enum):
    requested = "requested"
    searching_driver = "searching_driver"
    driver_assigned = "driver_assigned"
    driver_arrived = "driver_arrived"
    in_progress = "in_progress"
    completed = "completed"
    cancelled = "cancelled"
