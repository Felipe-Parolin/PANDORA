from accounts.models import User

from .models import Notification


def notify(recipients, *, kind, title, message, target_url, event_key):
    """Persist one in-app notification per recipient and business event."""
    for user in recipients:
        if user and user.is_active:
            Notification.objects.get_or_create(
                recipient=user,
                event_key=event_key,
                defaults={"kind": kind, "title": title, "message": message, "target_url": target_url},
            )


def users_with_acl(permission):
    return [user for user in User.objects.filter(is_active=True).select_related("access_group") if user.has_acl(permission)]
