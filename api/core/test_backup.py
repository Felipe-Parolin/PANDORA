from io import StringIO
import json
from pathlib import Path
import tempfile
from unittest.mock import patch
import zipfile

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase


class LocalBackupTests(SimpleTestCase):
    databases={'default'}

    def test_zip_contains_dump_media_and_checksums_but_no_configuration(self):
        directory=Path(settings.BASE_DIR.parent)/'tmp'
        directory.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='backup-test-',dir=directory) as temporary:
            root=Path(temporary).resolve()
            self.assertTrue(root.is_relative_to(directory.resolve()))
            media=root/'media';media.mkdir();(media/'sample.txt').write_text('mídia fictícia',encoding='utf-8')
            (root/'.env').write_text('CONFIGURACAO_PRIVADA=fixture',encoding='utf-8')
            binary=root/'pg_dump.exe';binary.touch();binary.with_name('pg_restore.exe').touch()
            def run(arguments,**kwargs):
                if '--file' in arguments:Path(arguments[arguments.index('--file')+1]).write_bytes(b'PGDMP-ficticio')
                self.assertNotIn('PGPASSWORD',str(arguments))
            target=root/'test.zip'
            with self.settings(MEDIA_ROOT=media),patch('core.management.commands.backup_local.subprocess.run',side_effect=run):
                call_command('backup_local',output=str(target),pg_dump=str(binary),stdout=StringIO())
            with zipfile.ZipFile(target) as archive:
                self.assertEqual(set(archive.namelist()),{'database.dump','media/sample.txt','manifest.json'})
                self.assertEqual(len(json.loads(archive.read('manifest.json'))['files_sha256']),2)
            with self.assertRaises(CommandError):call_command('backup_local',output=str(target),pg_dump=str(binary),stdout=StringIO())

    def test_backup_refuses_remote_host_and_path_outside_project(self):
        from django.db import connection
        with patch.dict(connection.settings_dict,{'HOST':'remote.invalid'}):
            with self.assertRaises(CommandError):call_command('backup_local',stdout=StringIO())
        with self.assertRaises(CommandError):call_command('backup_local',output=str(Path(settings.BASE_DIR).parent.parent/'outside.zip'),stdout=StringIO())
