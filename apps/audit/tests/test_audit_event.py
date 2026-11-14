from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.audit.models import AuditEvent
from apps.organizations.models import Diocese, Deanery, Parish
from apps.verification.models import MembershipApplication


class AuditEventModelTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.diocese = Diocese.objects.get(code="036")
        cls.deanery = Deanery.objects.create(
            diocese=cls.diocese,
            name="Audit Test Deanery",
            code="AUDIT-DEANERY",
        )
        cls.parish = Parish.objects.create(
            deanery=cls.deanery,
            name="Audit Test Parish",
        )
        cls.other_deanery = Deanery.objects.create(
            diocese=cls.diocese,
            name="Other Audit Deanery",
            code="OTHER-AUDIT",
        )
        cls.user = get_user_model().objects.create_user(
            username="audit_actor",
            password="test-only-password",
        )
        cls.content_type = ContentType.objects.get_for_model(
            MembershipApplication
        )

    def create_event(self, **overrides):
        values = {
            "actor": self.user,
            "actor_name_snapshot": "Audit Actor",
            "action": AuditEvent.Action.MEMBERSHIP_REVIEW_RECORDED,
            "content_type": self.content_type,
            "object_id": 1,
            "diocese": self.diocese,
            "deanery": self.deanery,
            "parish": self.parish,
            "metadata": {
                "review_level": "parish",
                "decision": "approved",
            },
        }
        values.update(overrides)
        return AuditEvent.objects.create(**values)

    def test_creates_event_with_actor_and_organizational_scope(self):
        event = self.create_event()

        self.assertEqual(event.actor, self.user)
        self.assertEqual(event.actor_name_snapshot, "Audit Actor")
        self.assertEqual(event.diocese, self.diocese)
        self.assertEqual(event.deanery, self.deanery)
        self.assertEqual(event.parish, self.parish)
        self.assertEqual(
            event.metadata,
            {
                "review_level": "parish",
                "decision": "approved",
            },
        )
        self.assertIsNotNone(event.created_at)

    def test_rejects_parish_from_another_deanery(self):
        other_parish = Parish.objects.create(
            deanery=self.other_deanery,
            name="Other Audit Parish",
        )

        with self.assertRaises(ValidationError):
            self.create_event(parish=other_parish)

    def test_accepts_another_deanery_within_the_diocese(self):
        other_parish = Parish.objects.create(
            deanery=self.other_deanery,
            name="Other Audit Deanery Parish",
        )

        event = self.create_event(
            deanery=self.other_deanery,
            parish=other_parish,
        )

        self.assertEqual(event.diocese, self.diocese)
        self.assertEqual(event.deanery, self.other_deanery)
        self.assertEqual(event.parish, other_parish)

    def test_rejects_instance_update(self):
        event = self.create_event()
        event.actor_name_snapshot = "Changed Actor"

        with self.assertRaisesMessage(
            ValidationError,
            "Audit events cannot be updated.",
        ):
            event.save()

        event.refresh_from_db()
        self.assertEqual(event.actor_name_snapshot, "Audit Actor")

    def test_rejects_queryset_update(self):
        event = self.create_event()

        with self.assertRaisesMessage(
            ValidationError,
            "Audit events cannot be updated.",
        ):
            AuditEvent.objects.filter(pk=event.pk).update(
                actor_name_snapshot="Changed Actor"
            )

    def test_rejects_bulk_update(self):
        event = self.create_event()
        event.actor_name_snapshot = "Changed Actor"

        with self.assertRaisesMessage(
            ValidationError,
            "Audit events cannot be updated.",
        ):
            AuditEvent.objects.bulk_update(
                [event],
                ["actor_name_snapshot"],
            )

    def test_rejects_instance_delete(self):
        event = self.create_event()

        with self.assertRaisesMessage(
            ValidationError,
            "Audit events cannot be deleted.",
        ):
            event.delete()

        self.assertTrue(AuditEvent.objects.filter(pk=event.pk).exists())

    def test_rejects_queryset_delete(self):
        event = self.create_event()

        with self.assertRaisesMessage(
            ValidationError,
            "Audit events cannot be deleted.",
        ):
            AuditEvent.objects.filter(pk=event.pk).delete()

        self.assertTrue(AuditEvent.objects.filter(pk=event.pk).exists())
