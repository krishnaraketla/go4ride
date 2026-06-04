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


class DriverStatus(str, enum.Enum):
    offline = "offline"
    online = "online"
    on_ride = "on_ride"


class KycStatus(str, enum.Enum):
    pending = "pending"
    submitted = "submitted"
    approved = "approved"
    rejected = "rejected"


class DocumentType(str, enum.Enum):
    license = "license"
    registration = "registration"
    insurance = "insurance"
    profile_photo = "profile_photo"


class DocumentStatus(str, enum.Enum):
    not_uploaded = "not_uploaded"
    pending = "pending"
    approved = "approved"
    rejected = "rejected"


class VehicleType(str, enum.Enum):
    auto = "auto"
    taxi = "taxi"
    cab = "cab"


class OnboardingStatus(str, enum.Enum):
    pending = "pending"
    documents_uploaded = "documents_uploaded"
    vehicle_submitted = "vehicle_submitted"
    under_review = "under_review"
    approved = "approved"
    rejected = "rejected"
