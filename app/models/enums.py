import enum


class UserRole(str, enum.Enum):
    rider = "rider"


class OTPPurpose(str, enum.Enum):
    login = "login"
    register = "register"


class RideStatus(str, enum.Enum):
    requested = "requested"
    searching_driver = "searching_driver"
    driver_assigned = "driver_assigned"
    driver_arrived = "driver_arrived"
    in_progress = "in_progress"
    completed = "completed"
    cancelled = "cancelled"
