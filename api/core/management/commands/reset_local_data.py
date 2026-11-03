import hashlib
import os
from pathlib import Path
import shutil
import subprocess
from uuid import uuid4

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from django.utils import timezone

from core.local_reset import ensure_local_database, reset_counts, reset_local_data, validate_admin


class Command(BaseCommand):
    help = "Limpa os dados locais, preservando um administrador. Sem --confirm-local-reset apenas apresenta contagens. Faz backup antes de limpar."

    def add_arguments(self, parser):
        parser.add_argument("--keep-user", type=int, required=True)
        parser.add_argument("--confirm-local-reset", action="store_true")
        parser.add_argument("--backup-dir", default=str(settings.BASE_DIR.parent / "backups"))
        parser.add_argument("--pg-dump", default="")

    def handle(self, *args, **options):
        ensure_local_database()
        try:
            validate_admin(options["keep_user"])
        except Exception as exc:
            raise CommandError("Não foi possível validar o administrador a preservar.") from exc
        counts = reset_counts()
        for label, count in sorted(counts.items()):
            if count:
                self.stdout.write(f"{label}: {count}")
        if not options["confirm_local_reset"]:
            self.stdout.write("Simulação concluída. Nenhum dado foi alterado.")
            return
        binary = options["pg_dump"] or shutil.which("pg_dump")
        if not binary or not Path(binary).is_file():
            raise CommandError("Informe --pg-dump com o executável do PostgreSQL para criar o backup obrigatório.")
        restore_binary = Path(binary).with_name("pg_restore.exe" if os.name == "nt" else "pg_restore")
        if not restore_binary.is_file():
            raise CommandError("pg_restore não encontrado para verificar o backup.")
        backup_dir = Path(options["backup_dir"]).resolve()
        backup_dir.mkdir(parents=True, exist_ok=True)
        target = backup_dir / f"pandora-before-reset-{timezone.now():%Y%m%dT%H%M%SZ}-{uuid4().hex[:8]}.dump"
        database = connection.settings_dict
        environment = os.environ.copy()
        environment.update(PGHOST=database.get("HOST") or "localhost", PGPORT=str(database.get("PORT") or 5432), PGUSER=database["USER"], PGPASSWORD=database.get("PASSWORD") or "", PGDATABASE=database["NAME"])
        # Credenciais ficam apenas no ambiente do subprocesso, sem impressão nem argumentos.
        flags = {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}
        try:
            subprocess.run([str(binary), "--format=custom", "--file", str(target)], env=environment, check=True, capture_output=True, timeout=180, **flags)
            subprocess.run([str(restore_binary), "--list", str(target)], check=True, capture_output=True, timeout=30, **flags)
        except (subprocess.SubprocessError, OSError) as exc:
            raise CommandError("Não foi possível criar/verificar o backup. Nenhum dado foi apagado.") from exc
        if target.stat().st_size == 0:
            raise CommandError("Backup vazio. Nenhum dado foi apagado.")
        with target.open("rb") as stream:
            checksum = hashlib.file_digest(stream, "sha256").hexdigest()
        target.with_suffix(".dump.sha256").write_text(f"{checksum}  {target.name}\n", encoding="utf-8")
        self.stdout.write(f"Backup verificado: {target}")
        result = reset_local_data(options["keep_user"])
        self.stdout.write(self.style.SUCCESS(f"Limpeza concluída: {result['cleared_tables']} tabelas vazias; somente o administrador {result['admin_id']} foi preservado."))
