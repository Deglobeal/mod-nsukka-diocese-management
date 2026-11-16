import base64
import hashlib
from django.core import signing
from django.http import JsonResponse
from django.views.decorators.http import require_POST
import binascii
from io import BytesIO

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import transaction
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods
from PIL import Image, UnidentifiedImageError

from apps.members.forms import MembershipRegistrationForm
from apps.members.passport_photo_processing import process_passport_photo
from apps.members.models import FirstMemberRegistrationAttempt
from apps.members.services.first_member_registration import (
    record_registration_attempt,
    redeem_registration_id,
)
from apps.members.services.registration_id_verification import (
    RegistrationIDVerificationError,
    read_registration_confirmation,
    revalidate_bootstrap_confirmation,
    revalidate_ordinary_sponsor,
    verify_registration_id,
)
from apps.notifications.services.sponsor_verification import (
    create_sponsor_verification_and_sms,
)
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



PASSPORT_PREVIEW_SIGNING_SALT = "members.passport-photo-preview"
PASSPORT_PREVIEW_MAX_AGE_SECONDS = 30 * 60


@require_POST
def process_passport_photo_preview(request):
    """Process a captured passport image before the applicant accepts it."""
    photo_data = request.POST.get("passport_photo_data", "")

    try:
        raw_photo, _extension = _passport_photo_from_post(photo_data)
        processed_photo = process_passport_photo(raw_photo)

        with Image.open(BytesIO(processed_photo)) as image:
            if image.format != "JPEG":
                raise ValidationError(
                    "Photo processing did not produce a valid JPEG."
                )
            image.verify()

        token = signing.dumps(
            {
                "sha256": hashlib.sha256(processed_photo).hexdigest(),
                "size": len(processed_photo),
            },
            salt=PASSPORT_PREVIEW_SIGNING_SALT,
        )

        processed_data = (
            "data:image/jpeg;base64,"
            + base64.b64encode(processed_photo).decode("ascii")
        )

        return JsonResponse(
            {
                "photo_data": processed_data,
                "photo_token": token,
            }
        )
    except ValidationError as error:
        message = error.messages[0] if error.messages else str(error)
        return JsonResponse({"error": message}, status=400)
    except (UnidentifiedImageError, OSError, ValueError):
        return JsonResponse(
            {"error": "The processed photo is invalid. Please retake it."},
            status=400,
        )


@require_POST
def verify_registration_sponsor(request):
    """Verify either an active sponsor ID or an authorized bootstrap ID."""
    sponsor_membership_id = request.POST.get("sponsor_membership_id", "")
    try:
        verified = verify_registration_id(
            sponsor_membership_id,
            session=request.session,
        )
    except RegistrationIDVerificationError as error:
        if sponsor_membership_id.strip().startswith("MOD036-"):
            record_registration_attempt(
                raw_id=sponsor_membership_id,
                outcome=FirstMemberRegistrationAttempt.Outcome.INVALID_ID,
                error_code="invalid_or_unavailable_id",
            )
        message = error.messages[0] if error.messages else str(error)
        return JsonResponse({"error": message}, status=400)
    if verified.kind == "first_member_bootstrap":
        return JsonResponse({
            "kind": verified.kind,
            "confirmation": verified.confirmation,
            "message": "Valid Diocese-issued first-member registration ID.",
        })
    phone = verified.sponsor_contact.recipient_phone
    masked_phone = f"{phone[:4]}{'*' * max(0, len(phone) - 8)}{phone[-4:]}"
    return JsonResponse({
        "kind": verified.kind,
        "confirmation": verified.confirmation,
        "name": verified.sponsor_contact.member.full_name,
        "registered_phone": masked_phone,
    })


@require_http_methods(["GET", "POST"])
def membership_registration(request):
    if request.method == "POST":
        # Passport photographs must still come from the camera capture.
        photo_data = request.POST.get("passport_photo_data", "")
        photo_token = request.POST.get("passport_photo_token", "")
        uploaded_files = request.FILES.copy()
        uploaded_files.pop("passport_photo", None)
        photo_error = None

        if photo_data:
            try:
                photo_bytes, _photo_extension = _passport_photo_from_post(
                    photo_data
                )

                if photo_token:
                    # A browser-accepted preview must be the exact processed
                    # image returned by our preview endpoint and still be valid.
                    token_data = signing.loads(
                        photo_token,
                        salt=PASSPORT_PREVIEW_SIGNING_SALT,
                        max_age=PASSPORT_PREVIEW_MAX_AGE_SECONDS,
                    )
                    if (
                        token_data.get("sha256")
                        != hashlib.sha256(photo_bytes).hexdigest()
                        or token_data.get("size") != len(photo_bytes)
                    ):
                        raise ValidationError(
                            "Your accepted photograph has changed. "
                            "Please capture and accept it again."
                        )
                    with Image.open(BytesIO(photo_bytes)) as image:
                        if image.format != "JPEG":
                            raise ValidationError(
                                "The accepted photograph must be a processed JPEG."
                            )
                        image.verify()
                else:
                    # Compatibility path for existing tests and older clients.
                    # The camera UI will submit a token after preview acceptance.
                    photo_bytes = process_passport_photo(photo_bytes)

                uploaded_files["passport_photo"] = SimpleUploadedFile(
                    "camera-capture.jpg",
                    photo_bytes,
                    content_type="image/jpeg",
                )
            except signing.BadSignature:
                photo_error = ValidationError(
                    "Your photo preview has expired or is invalid. "
                    "Please capture and accept your photograph again."
                )
            except ValidationError as error:
                photo_error = error

        form = MembershipRegistrationForm(request.POST, uploaded_files)
        form_is_valid = form.is_valid()
        registration_id = (request.POST.get("sponsor_membership_id") or "").strip()

        if photo_error:
            form.add_error("passport_photo", photo_error)
        elif not photo_data:
            form.add_error(
                "passport_photo",
                "Please capture and accept your passport photograph using the camera.",
            )

        sponsor_contact = None
        confirmation = None
        if form_is_valid and photo_data and not photo_error:
            try:
                confirmation = read_registration_confirmation(
                    registration_id,
                    form.cleaned_data.get("registration_id_confirmation"),
                    session=request.session,
                )
                if confirmation["kind"] == "ordinary_sponsor":
                    sponsor_contact = revalidate_ordinary_sponsor(
                        raw_id=registration_id, payload=confirmation
                    )
            except RegistrationIDVerificationError as error:
                form.add_error("sponsor_membership_id", error)

        if (
            form_is_valid and photo_data and not photo_error and confirmation
            and (sponsor_contact or confirmation.get("kind") == "first_member_bootstrap")
        ):
            application = form.save(commit=False)
            application.stage = MembershipApplication.Stage.PARISH_REVIEW
            application.member = None
            if confirmation["kind"] == "first_member_bootstrap":
                # The one-time secret belongs only in the verification request;
                # persist the token relation and hash, never its raw value.
                application.sponsor_membership_id = ""

            try:
                with transaction.atomic():
                    if confirmation["kind"] == "first_member_bootstrap":
                        revalidate_bootstrap_confirmation(
                            raw_id=registration_id,
                            payload=confirmation,
                        )
                    # The ModelForm assigns the validated signature upload.
                    # The model field retains its private storage and random path.
                    application.save()
                    if confirmation["kind"] == "first_member_bootstrap":
                        redeem_registration_id(raw_id=registration_id, application=application)
                    else:
                        create_sponsor_verification_and_sms(
                            application=application,
                            sponsor_contact=sponsor_contact,
                            request=request,
                        )
            except ValidationError:
                # A token can be revoked or become ineligible after the
                # verification request. The surrounding transaction rolls
                # back application creation and redemption together.
                for image_field in (
                    application.signature_image,
                    application.passport_photo,
                ):
                    if image_field.name:
                        try:
                            image_field.storage.delete(image_field.name)
                        except Exception:
                            pass
                if confirmation.get("kind") == "first_member_bootstrap":
                    record_registration_attempt(
                        raw_id=registration_id,
                        outcome=FirstMemberRegistrationAttempt.Outcome.INVALID_ID,
                        error_code="bootstrap_id_not_available_at_submission",
                    )
                form.add_error(
                    "sponsor_membership_id",
                    "This ID is invalid, inactive, expired, revoked, or not authorized for registration. Please verify it again.",
                )
                return render(
                    request,
                    "registration/registration.html",
                    {"form": form, "passport_photo_data": photo_data},
                )
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

                if confirmation and confirmation.get("kind") == "first_member_bootstrap":
                    record_registration_attempt(
                        raw_id=registration_id,
                        outcome=FirstMemberRegistrationAttempt.Outcome.REGISTRATION_FAILED,
                        error_code="application_save_failed",
                    )

                form.add_error(
                    None,
                    "We couldn't securely save your registration. "
                    "Please try again.",
                )
                return render(
                    request,
                    "registration/registration.html",
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

        if (
            registration_id
            and confirmation
            and confirmation.get("kind") == "first_member_bootstrap"
            and (not form_is_valid or photo_error)
        ):
            attempt_outcome = (
                FirstMemberRegistrationAttempt.Outcome.INVALID_ID
                if form.errors.get("sponsor_membership_id")
                else FirstMemberRegistrationAttempt.Outcome.FORM_INVALID
            )
            record_registration_attempt(
                raw_id=registration_id,
                outcome=attempt_outcome,
                error_code=(
                    "invalid_or_unavailable_id"
                    if attempt_outcome == FirstMemberRegistrationAttempt.Outcome.INVALID_ID
                    else "form_validation_failed"
                ),
            )

        return render(
            request,
            "registration/registration.html",
            {
                "form": form,
                "passport_photo_data": photo_data,
            },
        )
    else:
        form = MembershipRegistrationForm()

    return render(
        request,
        "registration/registration.html",
        {"form": form, "passport_photo_data": ""},
    )


def registration_received(request, application_id):
    allowed_ids = request.session.get("registration_application_ids", [])

    if application_id not in allowed_ids:
        raise Http404("Registration not found.")

    application = get_object_or_404(
        MembershipApplication,
        pk=application_id,
    )

    return render(
        request,
        "registration/registration_received.html",
        {"application": application},
    )
