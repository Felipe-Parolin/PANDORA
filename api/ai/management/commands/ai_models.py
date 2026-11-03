import requests
from django.core.management.base import BaseCommand, CommandError

from core.patterns import AISettings


class Command(BaseCommand):
    help = "Lista os modelos disponíveis na sua conta Groq e indica qual está configurado em AI_MODEL."

    def handle(self, *args, **options):
        config = AISettings.get_instance()
        if not config.api_key:
            raise CommandError("Defina GROQ_API_KEY no api/.env.")
        response = requests.get(f"{config.base_url}/models", headers={"Authorization": f"Bearer {config.api_key}"}, timeout=20)
        if response.status_code >= 400:
            raise CommandError(f"A Groq respondeu HTTP {response.status_code}.")
        ids = sorted(item["id"] for item in response.json().get("data", []))
        skip = ("whisper", "guard", "tts", "playai", "orpheus", "distil")
        chat = [i for i in ids if not any(word in i.lower() for word in skip)]
        audio = [i for i in ids if "whisper" in i.lower()]
        self.stdout.write(f"AI_MODEL atual: {config.model} -> {'OK' if config.model in ids else 'NÃO DISPONÍVEL'}")
        self.stdout.write(f"AI_TRANSCRIPTION_MODEL atual: {config.transcription_model} -> {'OK' if config.transcription_model in ids else 'NÃO DISPONÍVEL'}")
        self.stdout.write("\nModelos de chat disponíveis:\n  " + "\n  ".join(chat))
        self.stdout.write("\nModelos de transcrição disponíveis:\n  " + ("\n  ".join(audio) or "(nenhum)"))