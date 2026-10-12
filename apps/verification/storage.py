"""Private filesystem storage for membership evidence."""

from django.conf import settings
from django.core.files.storage import FileSystemStorage
from django.utils.deconstruct import deconstructible


@deconstructible
class PrivateEvidenceStorage(FileSystemStorage):
    """Store evidence privately and prohibit public URL generation."""

    def __init__(self):
        super().__init__(
            location=settings.PRIVATE_MEDIA_ROOT,
            base_url="",
        )

    def url(self, name):
        raise ValueError(
            "Membership evidence has no public URL. "
            "Use the authenticated evidence download endpoint."
        )


private_evidence_storage = PrivateEvidenceStorage()
