import enum


class UserRole(enum.Enum):
    Student = "Student"
    Employer = "Employer"
    PlacementOfficer = "PlacementOfficer"
    Admin = "Admin"


class CompanyType(enum.Enum):
    Startup = "Startup"
    Midsize = "Midsize"
    MNC = "MNC"


class InternshipType(enum.Enum):
    Remote = "Remote"
    Onsite = "Onsite"
    Hybrid = "Hybrid"


class JobType(enum.Enum):
    Full_Time = "Full-Time"
    Internship = "Internship"
    Contract = "Contract"
    Part_Time = "Part-Time"
    Campus_Driven = "Campus_Driven"


class JobApplicationStatus(enum.Enum):
    InProgress = "InProgress"
    Shortlisted = "Shortlisted"
    Rejected = "Rejected"
    Hired = "Hired"
    Offered = "Offered"


class CourseLevelEnum(enum.Enum):
    Beginner = "Beginner"
    Intermediate = "Intermediate"
    Advanced = "Advanced"


class CourseStatusEnum(enum.Enum):
    NotStarted = "Not Started"
    InProgress = "In Progress"
    Completed = "Completed"


class RoadmapStatusEnum(enum.Enum):
    NotStarted = "Not Started"
    InProgress = "In Progress"
    Completed = "Completed"


class ResumeTypeEnum(enum.Enum):
    Uploaded = "Uploaded"
    Uplifted = "Uplifted"


class ResultEnum(enum.Enum):
    correct = "correct"
    wrong = "wrong"


class OfferLetterEnum(enum.Enum):
    Signed = "signed"
    Unsigned = "unsigned"


class SlotStatus(str, enum.Enum):
    AVAILABLE = "available"
    BOOKED = "booked"
    EXPIRED = "expired"
    CANCELLED = "cancelled"