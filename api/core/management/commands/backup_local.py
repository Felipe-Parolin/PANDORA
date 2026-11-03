"""Backup PostgreSQL + mídias para compartilhar uma base local de testes."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import zipfile

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from django.utils import timezone


def find_pg_dump(explicit=""):
    if explicit:
        path=Path(explicit)
        if path.is_file():
            return path
        raise CommandError("O executável informado em --pg-dump não foi encontrado.")
    binary=shutil.which("pg_dump")
    if binary:
        return Path(binary)
    directory=Path(os.environ.get("ProgramFiles","C:/Program Files"))/"PostgreSQL"
    candidates=list(directory.glob("*/bin/pg_dump.exe"))
    if candidates:
        return max(candidates,key=lambda path: tuple(int(part) for part in path.parents[1].name.split(".") if part.isdigit()))
    raise CommandError("pg_dump não encontrado. Instale as ferramentas do PostgreSQL ou informe --pg-dump com o caminho do executável.")


class Command(BaseCommand):
    help="Cria ZIP local com dump PostgreSQL, mídias e manifesto de integridade. Não inclui configurações nem senhas em texto."

    def add_arguments(self,parser):
        parser.add_argument("--output",help="Arquivo ZIP dentro do projeto; padrão: backups/pandora-teste-DATA.zip")
        parser.add_argument("--pg-dump",default="",help="Caminho opcional do pg_dump da mesma versão do servidor ou superior.")

    def handle(self,*args,**options):
        database=connection.settings_dict
        if connection.vendor!="postgresql" or database.get("HOST","") not in {"","localhost","127.0.0.1","::1"}:
            raise CommandError("Este comando aceita somente PostgreSQL local.")
        workspace=settings.BASE_DIR.parent.resolve()
        output=Path(options["output"]).resolve() if options["output"] else workspace/"backups"/f"pandora-teste-{timezone.now():%Y%m%dT%H%M%SZ}.zip"
        if not output.is_relative_to(workspace) or output.suffix.lower()!=".zip":
            raise CommandError("Escolha um arquivo .zip dentro da pasta do projeto.")
        if output.exists():
            raise CommandError("O arquivo já existe. Escolha outro nome para preservar o backup anterior.")
        binary=find_pg_dump(options["pg_dump"])
        restore=binary.with_name("pg_restore.exe" if os.name=="nt" else "pg_restore")
        if not restore.is_file():
            raise CommandError("pg_restore não encontrado ao lado do pg_dump; a verificação é obrigatória.")
        output.parent.mkdir(parents=True,exist_ok=True)
        environment=os.environ.copy()
        environment.update(PGHOST=database.get("HOST") or "localhost",PGPORT=str(database.get("PORT") or 5432),PGUSER=database["USER"],PGPASSWORD=database.get("PASSWORD") or "",PGDATABASE=database["NAME"])
        flags={"creationflags":subprocess.CREATE_NO_WINDOW} if os.name=="nt" else {}
        with tempfile.TemporaryDirectory(prefix="pandora-backup-",dir=output.parent) as temporary:
            temporary=Path(temporary).resolve()
            if not temporary.is_relative_to(output.parent):
                raise CommandError("Diretório temporário fora do destino permitido.")
            dump=temporary/"database.dump"
            try:
                subprocess.run([str(binary),"--format=custom","--no-owner","--no-acl","--file",str(dump)],env=environment,check=True,capture_output=True,timeout=180,**flags)
                subprocess.run([str(restore),"--list",str(dump)],check=True,capture_output=True,timeout=30,**flags)
            except (subprocess.SubprocessError,OSError):
                raise CommandError("Falha ao criar ou verificar o dump. Confira a versão das ferramentas e o acesso ao PostgreSQL; nenhum dado foi alterado.")
            if not dump.exists() or not dump.stat().st_size:
                raise CommandError("O dump está vazio. O backup não foi criado.")
            staged=temporary/"backup.zip"
            files={}
            with zipfile.ZipFile(staged,"w",zipfile.ZIP_DEFLATED) as archive:
                sources=[(dump,"database.dump")]
                media=Path(settings.MEDIA_ROOT).resolve()
                if media.exists():
                    sources.extend((file,"media/"+file.relative_to(media).as_posix()) for file in sorted(media.rglob("*")) if file.is_file() and not file.is_symlink() and file.resolve().is_relative_to(media))
                for file,name in sources:
                    archive.write(file,name)
                    with file.open("rb") as stream:
                        files[name]=hashlib.file_digest(stream,"sha256").hexdigest()
                archive.writestr("manifest.json",json.dumps({"schema_version":1,"created_at":timezone.now().isoformat(),"database":database["NAME"],"format":"PostgreSQL custom","files_sha256":files},ensure_ascii=False,indent=2))
            with zipfile.ZipFile(staged) as archive:
                if archive.testzip() is not None:
                    raise CommandError("O ZIP não passou pela verificação. O backup não foi concluído.")
            # Criação exclusiva: não sobrescreve um backup criado por outra execução.
            with output.open("xb") as destination,staged.open("rb") as source:
                shutil.copyfileobj(source,destination)
        self.stdout.write(self.style.SUCCESS(f"Backup verificado: {output} ({len(files)-1} arquivo(s) de mídia). Nenhuma configuração .env foi incluída."))
