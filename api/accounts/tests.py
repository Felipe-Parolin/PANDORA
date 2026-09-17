from django.test import TestCase
from rest_framework.test import APIClient

from .models import AccessGroup, User


class ACLTests(TestCase):
    def setUp(self):
        self.group = AccessGroup.objects.create(
            name="Consulta de frota",
            permissions=["assets.view"],
        )
        self.user = User.objects.create_user(
            "acl@example.com",
            "strong-password",
            full_name="Usuário ACL",
            access_group=self.group,
        )
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def test_acl_allows_only_selected_capability(self):
        self.assertTrue(self.user.has_acl("assets.view"))
        self.assertFalse(self.user.has_acl("assets.manage"))
        self.assertEqual(self.client.get("/api/equipment/").status_code, 200)
        self.assertEqual(self.client.post("/api/categories/", {"name": "Bloqueada"}).status_code, 403)

    def test_current_user_exposes_acl(self):
        response = self.client.get("/api/auth/me/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["access_group_name"], "Consulta de frota")
        self.assertEqual(response.data["permissions"], ["assets.view"])
