from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from accounts.models import AccessGroup, User
from .models import Equipment, EquipmentCategory, MediaAsset


class EquipmentQRTests(TestCase):
    def setUp(self):
        group = AccessGroup.objects.create(name="Frota", permissions=["assets.view", "assets.manage"])
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

    def test_equipment_filters_are_applied_on_server(self):
        other = Equipment.objects.create(
            category=self.equipment.category, name="Betoneira", brand="Outra", model="B2",
            serial_number="QR-002", internal_code="EQ-OTHER", daily_rate=80,
            status=Equipment.Status.MAINTENANCE,
        )
        response = self.client.get("/api/equipment/?search=EQ-OTHER&status=MAINTENANCE")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["id"], other.id)

    def test_category_can_be_nested(self):
        parent = EquipmentCategory.objects.create(name="Concretagem")
        child_response = self.client.post(
            "/api/categories/", {"name": "Betoneiras", "parent": parent.id}, format="json"
        )
        self.assertEqual(child_response.status_code, 201)
        self.assertEqual(child_response.data["parent"], parent.id)
        self.assertEqual(child_response.data["parent_name"], "Concretagem")



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
        self.assertEqual(self.client.get(f"{url}?download=1").status_code, 403)

    def test_pdf_is_inline_office_documents_download_and_missing_file_is_reported(self):
        from io import BytesIO
        from pypdf import PdfWriter

        output = BytesIO()
        writer = PdfWriter()
        writer.add_blank_page(width=100, height=100)
        writer.write(output)
        pdf = MediaAsset.objects.create(name="Manual", category="MANUAL", equipment=self.equipment, uploaded_by=self.user,
                                        file=SimpleUploadedFile("manual.pdf", output.getvalue(), content_type="application/pdf"))
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

    def test_empty_file_and_missing_asset_return_404(self):
        empty = MediaAsset.objects.create(name="Sem arquivo", category="OTHER", equipment=self.equipment, uploaded_by=self.user, file="")
        self.assertEqual(self.client.get(f"/api/media/{empty.pk}/content/").status_code, 404)
        self.assertEqual(self.client.get("/api/media/999999/content/").status_code, 404)

    def test_authentication_required_for_preview_and_download(self):
        item = MediaAsset.objects.create(name="Foto", category="PHOTO", equipment=self.equipment, uploaded_by=self.user, file="foto.jpg")
        self.client.force_authenticate(None)
        for suffix in ("", "?download=1"):
            self.assertEqual(self.client.get(f"/api/media/{item.pk}/content/{suffix}").status_code, 401)

    def test_media_listing_has_all_pages_and_keeps_equipment_filter(self):
        MediaAsset.objects.bulk_create([
            MediaAsset(name=f"Arquivo {index}", category="OTHER", equipment=self.equipment, uploaded_by=self.user, file=f"file-{index}.docx")
            for index in range(23)
        ])
        first = self.client.get(f"/api/media/?equipment={self.equipment.pk}")
        second = self.client.get(f"/api/media/?equipment={self.equipment.pk}&page=2")
        self.assertEqual(first.data["count"], 23)
        self.assertEqual(len(first.data["results"]), 20)
        self.assertEqual(len(second.data["results"]), 3)
        self.assertIsNone(second.data["next"])
        self.assertTrue(all(item["equipment"] == self.equipment.pk for item in first.data["results"] + second.data["results"]))

    def test_upload_edit_delete_and_equipment_link_are_preserved(self):
        self.group.permissions = ["media.view", "media.manage"]
        self.group.save()
        self.user.refresh_from_db()
        response = self.client.post("/api/media/", {
            "name": "Documento", "category": "DOCUMENT", "equipment": self.equipment.pk,
            "file": SimpleUploadedFile("anexo.docx", b"documento de teste"),
        }, format="multipart")
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["equipment"], self.equipment.pk)
        self.assertEqual(response.data["uploaded_by"], self.user.pk)
        url = f"/api/media/{response.data['id']}/"
        self.assertEqual(self.client.patch(url, {"description": "Atualizado"}, format="json").status_code, 200)
        content = self.client.get(f"{url}content/?download=1")
        self.assertEqual(b"".join(content.streaming_content), b"documento de teste")
        self.assertEqual(self.client.delete(url).status_code, 204)
        self.assertEqual(self.client.get(f"{url}content/").status_code, 404)
