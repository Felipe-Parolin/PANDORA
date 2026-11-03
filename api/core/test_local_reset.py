from datetime import timedelta
from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection
from django.test import TransactionTestCase
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import AccessGroup, User
from commercial.models import Receivable
from customers.models import Customer
from core.local_reset import reset_local_data, reset_counts, ensure_local_database
from core.models import AuditLog


class LocalResetTests(TransactionTestCase):
    def setUp(self):
        self.group=AccessGroup.objects.create(name='Admin preservado',permissions=['*'])
        self.admin=User.objects.create_user('admin-reset@example.invalid','test',full_name='Admin de teste',role='ADMIN',access_group=self.group)
        other_group=AccessGroup.objects.create(name='Grupo a limpar',permissions=['customers.view'])
        self.other=User.objects.create_user('other-reset@example.invalid','test',full_name='Outro usuário',access_group=other_group)
        self.customer=Customer.objects.create(person_type='PF',name='Cliente a limpar',document='12345678909',phone='19999999999')
        today=timezone.localdate()
        title=Receivable.objects.create(customer=self.customer,description='Conta a limpar',issue_date=today,due_date=today+timedelta(days=1),amount=100,created_by=self.other)
        client=APIClient();client.force_authenticate(self.admin)
        preview=client.post('/api/receivables/settlement-preview/',{'customer':self.customer.pk,'receivable_ids':[title.pk],'payment_date':str(today)},format='json').data
        from uuid import uuid4
        response=client.post('/api/receivables/settle/',{'customer':self.customer.pk,'receivable_ids':[title.pk],'payment_date':str(today),'method':'PIX','idempotency_key':str(uuid4()),'calculation_token':preview['calculation_token'],'expected_total':preview['total']},format='json')
        self.assertEqual(response.status_code,201,response.data)

    def test_simulation_does_not_mutate_data_or_call_backup(self):
        with patch('core.management.commands.reset_local_data.subprocess.run') as process:
            call_command('reset_local_data',keep_user=self.admin.pk,stdout=StringIO())
            process.assert_not_called()
        self.assertEqual(User.objects.count(),2);self.assertTrue(Customer.objects.exists())

    def test_reset_clears_protected_graph_and_preserves_admin_credentials(self):
        if connection.vendor!='postgresql':self.skipTest('Limpeza exige PostgreSQL local')
        old=(self.admin.password,self.admin.access_group_id)
        result=reset_local_data(self.admin.pk)
        self.assertEqual(result['users'],1)
        self.assertEqual(User.objects.count(),1);self.assertEqual(AccessGroup.objects.count(),1)
        self.admin.refresh_from_db()
        self.assertEqual((self.admin.password,self.admin.access_group_id),old)
        self.assertTrue(self.admin.check_password('test'));self.assertTrue(self.admin.has_acl('commercial.receivables.manage'))
        self.assertFalse(any(reset_counts().values()));self.assertFalse(AuditLog.objects.exists())
        client=APIClient();client.force_authenticate(self.admin)
        self.assertEqual(client.get('/api/auth/me/').status_code,200)
        self.assertEqual(client.get('/api/receivables/customers/').data['count'],0)

    def test_remote_database_or_non_admin_is_rejected_without_mutation(self):
        with patch.dict(connection.settings_dict,{'HOST':'remote.invalid'}):
            with self.assertRaises(CommandError):ensure_local_database()
        with self.assertRaises(CommandError):reset_local_data(self.other.pk)
        self.assertEqual(User.objects.count(),2);self.assertTrue(Customer.objects.exists())

    def test_backup_failure_prevents_cleanup(self):
        with patch('core.management.commands.reset_local_data.Path.is_file',return_value=True),patch('core.management.commands.reset_local_data.subprocess.run',side_effect=OSError('Falha simulada')):
            with self.assertRaises(CommandError):
                call_command('reset_local_data',keep_user=self.admin.pk,confirm_local_reset=True,pg_dump='pg_dump.exe',stdout=StringIO())
        self.assertEqual(User.objects.count(),2);self.assertTrue(Customer.objects.exists())
