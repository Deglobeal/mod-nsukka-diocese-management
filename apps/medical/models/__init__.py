"""Model package for medical. Keep each Django model in its own module.

Example future layout: from .member import Member
Do not combine unrelated model classes into one file.
"""
from .medical_access_event import MedicalAccessEvent
from .medical_record import MedicalRecord
from .medical_staff_assignment import MedicalStaffAssignment
from .member_medical_profile import MemberMedicalProfile
from .member_medical_profile_revision import MemberMedicalProfileRevision

__all__ = [
    "MedicalAccessEvent",
    "MedicalRecord",
    "MedicalStaffAssignment",
    "MemberMedicalProfile",
    "MemberMedicalProfileRevision",
]
