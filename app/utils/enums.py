import enum

class SenderType(enum.Enum):
    user = "user"
    ai = "ai"

class UserRole(enum.Enum):
    ADMIN = "Administrator"
    USER = "Normal user"
    SPECIALIST = "Specialist"
    GUEST = "Guest"


class UserGender(enum.Enum):
    MALE = "Male"
    FEMALE = "Female"
    OTHER = "Other"
