import base64
import binascii
from io import BytesIO

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods
from PIL import Image, UnidentifiedImageError

from apps.members.forms import MembershipRegistrationForm
from apps.verification.models import MembershipApplication


MAX_PASSPORT_PHOTO_BYTES = 5 * 1024 * 1024
PASSPORT_PREFIXES = {
    "data:image/jpeg;base64,": ("jpg", "JPEG"),
    "data:image/png;base64,": ("png", "PNG"),
}


def _passport_photo_from_post(value):
    """Decode and verify a JPEG/PNG captured by the registration camera."""
    if not value:
        raise ValidationError(
            "Please capture and accept your passport photograph using the camera."
        )

    prefix = next(
        (item for item in PASSPORT_PREFIXES if value.startswith(item)),
        None,
    )
    if prefix is None:
        raise ValidationError(
            "The passport photograph must be captured as a JPEG or PNG image."
        )

    encoded = value[len(prefix):]
    if not encoded or len(encoded) > (MAX_PASSPORT_PHOTO_BYTES * 4 // 3 + 8):
        raise ValidationError(
            "The captured photograph is empty or exceeds the 5 MB limit."
        )

    try:
        raw = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError):
        raise ValidationError("The captured photograph is invalid. Please retake it.")

    if not raw or len(raw) > MAX_PASSPORT_PHOTO_BYTES:
        raise ValidationError("The captured photograph must not exceed 5 MB.")

    extension, expected_format = PASSPORT_PREFIXES[prefix]
    try:
        with Image.open(BytesIO(raw)) as image:
            if image.format != expected_format:
                raise ValidationError(
                    "The captured image does not match its declared format."
                )
            width, height = image.size
            if width < 100 or height < 100 or width > 4000 or height > 4000:
                raise ValidationError(
                    "The photograph dimensions are invalid. Please retake it."
                )
            image.verify()
    except ValidationError:
        raise
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError):
        raise ValidationError(
            "The captured photograph could not be read. Please retake it."
        )

    return raw, extension


@require_http_methods(["GET", "POST"])
def membership_registration(request):
    if request.method == "POST":
        # Passport photographs must still come from the camera capture.
        photo_data = request.POST.get("passport_photo_data", "")
        uploaded_files = request.FILES.copy()
        uploaded_files.pop("passport_photo", None)
        photo_error = None

        if photo_data:
            try:
                photo_bytes, photo_extension = _passport_photo_from_post(
                    photo_data
                )
                uploaded_files["passport_photo"] = SimpleUploadedFile(
                    f"camera-capture.{photo_extension}",
                    photo_bytes,
                    content_type=(
                        "image/jpeg" if photo_extension == "jpg" else "image/png"
                    ),
                )
            except ValidationError as error:
                photo_error = error

        form = MembershipRegistrationForm(request.POST, uploaded_files)
        form_is_valid = form.is_valid()

        if photo_error:
            form.add_error("passport_photo", photo_error)
        elif not photo_data:
            form.add_error(
                "passport_photo",
                "Please capture and accept your passport photograph using the camera.",
            )

        if form_is_valid and photo_data and not photo_error:
            application = form.save(commit=False)
            application.stage = MembershipApplication.Stage.PARISH_REVIEW
            application.member = None

            try:
                with transaction.atomic():
                    # The ModelForm assigns the validated signature upload.
                    # The model field retains its private storage and random path.
                    application.save()
            except Exception:
                # Database transactions cannot roll back filesystem writes.
                for image_field in (
                    application.signature_image,
                    application.passport_photo,
                ):
                    if image_field.name:
                        try:
                            image_field.storage.delete(image_field.name)
                        except Exception:
                            pass

                form.add_error(
                    None,
                    "We couldn't securely save your registration. "
                    "Please try again.",
                )
                return render(
                    request,
                    "members/registration.html",
                    {
                        "form": form,
                        "passport_photo_data": photo_data,
                    },
                    status=500,
                )

            # Permit PDF downloads only from the submitting browser session.
            allowed_ids = request.session.get(
                "registration_application_ids", []
            )
            if application.pk not in allowed_ids:
                allowed_ids.append(application.pk)
            request.session["registration_application_ids"] = allowed_ids
            request.session.modified = True

            return redirect(
                "members:registration_received",
                application_id=application.pk,
            )

        return render(
            request,
            "members/registration.html",
            {
                "form": form,
                "passport_photo_data": photo_data,
            },
        )
    else:
        form = MembershipRegistrationForm()

    return render(
        request,
        "members/registration.html",
        {"form": form, "passport_photo_data": ""},
    )


def registration_received(request, application_id):
    application = get_object_or_404(
        MembershipApplication,
        pk=application_id,
    )

    return render(
        request,
        "members/registration_received.html",
        {"application": application},
    )
