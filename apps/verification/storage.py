"""Private storage for membership evidence."""

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import FileSystemStorage
from django.utils.deconstruct import deconstructible


@deconstructible
class PrivateEvidenceStorage(FileSystemStorage):
    """Store evidence privately and prohibit public URL generation.

    Local environments use Django's filesystem storage. Production uses a
    private Vercel Blob store because Vercel deployment filesystems are
    read-only and ephemeral.
    """

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

    @property
    def uses_blob_storage(self):
        return getattr(settings, "PRIVATE_MEDIA_BACKEND", "filesystem") == "vercel_blob"

    @staticmethod
    def _blob_client():
        from vercel.blob import sync as blob

        return blob

    def _save(self, name, content):
        if not self.uses_blob_storage:
            return super()._save(name, content)

        content.seek(0)
        uploaded = self._blob_client().put_blob(
            name,
            content.file,
            content_length=content.size,
            content_type=getattr(content, "content_type", None),
            access="private",
        )
        return uploaded.pathname

    def _open(self, name, mode="rb"):
        if not self.uses_blob_storage:
            return super()._open(name, mode)
        if mode != "rb":
            raise ValueError("Private evidence can only be opened for reading.")

        result = self._blob_client().get_blob(name, access="private")
        if result is None:
            raise FileNotFoundError(name)
        return ContentFile(result.body, name=name)

    def exists(self, name):
        if not self.uses_blob_storage:
            return super().exists(name)
        try:
            self._blob_client().head_blob(name)
        except self._blob_client().BlobNotFoundError:
            return False
        return True

    def size(self, name):
        if not self.uses_blob_storage:
            return super().size(name)
        return self._blob_client().head_blob(name).size

    def delete(self, name):
        if not self.uses_blob_storage:
            return super().delete(name)
        self._blob_client().delete_blob(name)

    def path(self, name):
        if self.uses_blob_storage:
            raise NotImplementedError(
                "Private evidence is stored remotely and has no local filesystem path."
            )
        return super().path(name)


private_evidence_storage = PrivateEvidenceStorage()
