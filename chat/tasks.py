import logging
from celery import shared_task
from django.utils import timezone
from django.contrib.auth import get_user_model

logger = logging.getLogger(__name__)
User = get_user_model()


# ─────────────────────────────────────────────────────────────────────────────
# TASK 1: Send message notification (async, non-blocking)
# Called immediately when a message is received via WebSocket
# ─────────────────────────────────────────────────────────────────────────────
@shared_task(bind=True, max_retries=3, default_retry_delay=5)
def send_message_notification(self, message_id):
    """
    Triggered when a new message is sent.
    Can be extended to send push notifications, emails, etc.
    """
    try:
        from chat.models import Message, ConversationParticipant

        message = Message.objects.select_related(
            'sender', 'conversation'
        ).get(id=message_id)

        participants = ConversationParticipant.objects.filter(
            conversation=message.conversation
        ).exclude(user=message.sender).select_related('user')

        sender_name = message.sender.get_full_name() or message.sender.username
        preview = message.content[:100] if message.content else 'Sent an attachment'

        for membership in participants:
            recipient = membership.user
            logger.info(
                f'[Notification] To: {recipient.email} | '
                f'From: {sender_name} | '
                f'Message: {preview[:50]}'
            )
            # ── Extend here: send email, FCM push, etc. ──
            # send_push_notification(recipient, sender_name, preview)
            # send_email_notification(recipient, message)

        return {
            'message_id': str(message_id),
            'recipients': participants.count(),
            'status': 'ok',
        }

    except Exception as exc:
        logger.error(f'send_message_notification failed: {exc}')
        raise self.retry(exc=exc)


# ─────────────────────────────────────────────────────────────────────────────
# TASK 2: Update user online status
# Called on WebSocket connect/disconnect
# ─────────────────────────────────────────────────────────────────────────────
@shared_task(bind=True, max_retries=3)
def update_user_online_status(self, user_id, is_online):
    """Update is_online + last_seen in DB asynchronously."""
    try:
        updates = {'is_online': is_online}
        if not is_online:
            updates['last_seen'] = timezone.now()
        User.objects.filter(id=user_id).update(**updates)
        logger.info(f'[Presence] User {user_id} → {"online" if is_online else "offline"}')
        return {'user_id': str(user_id), 'is_online': is_online}
    except Exception as exc:
        logger.error(f'update_user_online_status failed: {exc}')
        raise self.retry(exc=exc)


# ─────────────────────────────────────────────────────────────────────────────
# TASK 3: Clean up soft-deleted messages (scheduled periodic task)
# Runs every day at midnight via Celery Beat
# ─────────────────────────────────────────────────────────────────────────────
@shared_task
def cleanup_deleted_messages():
    """
    Hard-delete messages that were soft-deleted more than 30 days ago.
    """
    from chat.models import Message
    from datetime import timedelta

    cutoff = timezone.now() - timedelta(days=30)
    deleted_qs = Message.objects.filter(is_deleted=True, updated_at__lt=cutoff)
    count = deleted_qs.count()
    deleted_qs.delete()
    logger.info(f'[Cleanup] Hard-deleted {count} old soft-deleted messages')
    return {'deleted': count}


# ─────────────────────────────────────────────────────────────────────────────
# TASK 4: Mark inactive users as offline (scheduled periodic task)
# Runs every 5 minutes via Celery Beat
# ─────────────────────────────────────────────────────────────────────────────
@shared_task
def mark_inactive_users_offline():
    """
    If a user is marked online but hasn't been seen in 10 minutes,
    force them offline (handles crash/disconnect edge cases).
    """
    from datetime import timedelta

    cutoff = timezone.now() - timedelta(minutes=10)
    updated = User.objects.filter(
        is_online=True,
        last_seen__lt=cutoff
    ).update(is_online=False)
    if updated:
        logger.info(f'[Presence] Marked {updated} stale users as offline')
    return {'updated': updated}


# ─────────────────────────────────────────────────────────────────────────────
# TASK 5: Generate conversation summary stats (on-demand)
# ─────────────────────────────────────────────────────────────────────────────
@shared_task
def generate_conversation_stats(conversation_id):
    """Build stats for a conversation (message count, active users, etc.)"""
    try:
        from chat.models import Conversation, Message

        conv = Conversation.objects.get(id=conversation_id)
        total_messages   = Message.objects.filter(conversation=conv, is_deleted=False).count()
        deleted_messages = Message.objects.filter(conversation=conv, is_deleted=True).count()
        participants     = conv.participants.count()

        stats = {
            'conversation_id': str(conversation_id),
            'total_messages':  total_messages,
            'deleted_messages': deleted_messages,
            'participants':    participants,
            'generated_at':    timezone.now().isoformat(),
        }
        logger.info(f'[Stats] Conversation {conversation_id}: {stats}')
        return stats

    except Exception as exc:
        logger.error(f'generate_conversation_stats failed: {exc}')
        return {'error': str(exc)}


# ─────────────────────────────────────────────────────────────────────────────
# TASK 6: Bulk mark messages as read (async to avoid blocking WS response)
# ─────────────────────────────────────────────────────────────────────────────
@shared_task
def bulk_mark_messages_read(conversation_id, user_id):
    """Mark all unread messages in a conversation as read for a user."""
    try:
        from chat.models import Message, MessageReadReceipt, ConversationParticipant

        messages = Message.objects.filter(
            conversation_id=conversation_id,
            is_deleted=False
        ).exclude(sender_id=user_id)

        created = 0
        for msg in messages:
            _, was_created = MessageReadReceipt.objects.get_or_create(
                message=msg, user_id=user_id
            )
            if was_created:
                created += 1

        ConversationParticipant.objects.filter(
            conversation_id=conversation_id,
            user_id=user_id
        ).update(last_read_at=timezone.now())

        logger.info(f'[ReadReceipts] Marked {created} messages read for user {user_id}')
        return {'marked_read': created}

    except Exception as exc:
        logger.error(f'bulk_mark_messages_read failed: {exc}')
        return {'error': str(exc)}