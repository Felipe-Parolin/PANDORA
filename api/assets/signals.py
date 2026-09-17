from django.db.models.signals import post_delete
from django.dispatch import receiver

from .models import MediaAsset


@receiver(post_delete, sender=MediaAsset)
def delete_media_file(sender, instance, **kwargs):
    if instance.file:
        instance.file.delete(save=False)
