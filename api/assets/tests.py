from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from accounts.models import AccessGroup, User
from .models import Equipment, EquipmentCategory, MediaAsset


class EquipmentQRTests(TestCase):
    def setUp(self):
        group = AccessGroup.objects.create(name="Frota", permissions=["assets.view"])
        user = User.objects.create_user("fleet@example.com", "strong-password", full_name="Frota", access_group=group)
        category = EquipmentCategory.objects.create(name="Teste QR", default_daily_rate=100)
        self.equipment = Equipment.objects.create(category=category, name="Compactador", brand="Marca", model="M1", serial_number="QR-001", internal_code="EQ-QR", daily_rate=100)
        self.client = APIClient()
        self.client.force_authenticate(user)

    def test_qr_endpoint_returns_png_and_resolves_token(self):
        image = self.client.get(f"/api/equipment/{self.equipment.id}/qr-code/")
        self.assertEqual(image.status_code, 200)
        self.assertEqual(image["Content-Type"], "image/png")
        self.assertGreater(len(image.content), 100)

        resolved = self.client.get(f"/api/equipment/resolve-qr/?token={self.equipment.qr_code_token}")
        self.assertEqual(resolved.status_code, 200)
        self.assertEqual(resolved.data["internal_code"], "EQ-QR")


@override_settings(STORAGES={"default": {"BACKEND": "django.core.files.storage.InMemoryStorage"}})
class MediaPreviewTests(TestCase):
    def setUp(self):
        self.group = AccessGroup.objects.create(name="Consulta mídias", permissions=["media.view"])
        self.user = User.objects.create_user("media@example.invalid", "test", full_name="Mídias", access_group=self.group)
        category = EquipmentCategory.objects.create(name="Mídias", default_daily_rate=100)
        self.equipment = Equipment.objects.create(category=category, name="Equipamento", brand="Teste", model="M1", serial_number="MEDIA-1", internal_code="MEDIA-1", daily_rate=100)
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def test_preview_stream_and_download_require_media_permission(self):
        item = MediaAsset.objects.create(name="Foto", category="PHOTO", equipment=self.equipment, uploaded_by=self.user,
                                         file=SimpleUploadedFile("foto.png", b"image-test-fixture", content_type="image/png"))
        url = f"/api/media/{item.pk}/content/"
        preview = self.client.get(url)
        self.assertEqual(preview.status_code, 200)
        self.assertEqual(preview["Content-Type"], "image/png")
        self.assertIn("inline", preview["Content-Disposition"])
        self.assertEqual(b"".join(preview.streaming_content), b"image-test-fixture")
        download = self.client.get(f"{url}?download=1")
        self.assertIn("attachment", download["Content-Disposition"])
        self.assertTrue(b"".join(download.streaming_content))
        self.group.permissions = ["assets.view"]
        self.group.save()
        self.user.refresh_from_db()
        self.client.force_authenticate(self.user)
        self.assertEqual(self.client.get(url).status_code, 403)

    def test_pdf_is_inline_office_documents_download_and_missing_file_is_reported(self):
        pdf = MediaAsset.objects.create(name="Manual", category="MANUAL", equipment=self.equipment, uploaded_by=self.user,
                                        file=SimpleUploadedFile("manual.pdf", b"%PDF-test-fixture", content_type="application/pdf"))
        response = self.client.get(f"/api/media/{pdf.pk}/content/")
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertIn("inline", response["Content-Disposition"])
        self.assertTrue(b"".join(response.streaming_content))
        office = MediaAsset.objects.create(name="Documento", category="DOCUMENT", equipment=self.equipment, uploaded_by=self.user,
                                           file=SimpleUploadedFile("documento.docx", b"test-document"))
        response = self.client.get(f"/api/media/{office.pk}/content/")
        self.assertIn("attachment", response["Content-Disposition"])
        self.assertEqual(response["X-Content-Type-Options"], "nosniff")
        self.assertTrue(b"".join(response.streaming_content))
        missing = MediaAsset.objects.create(name="Indisponível", category="DOCUMENT", equipment=self.equipment, uploaded_by=self.user, file="missing.pdf")
        self.assertEqual(self.client.get(f"/api/media/{missing.pk}/content/").status_code, 404)
