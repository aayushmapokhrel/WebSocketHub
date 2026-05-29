import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.utils import timezone
from chat.models import (
    Conversation,
    Message,
    MessageReadReceipt,
    ConversationParticipant,
)
from chat.serializers import MessageSerializer


class ChatConsumer(AsyncWebsocketConsumer):

    async def connect(self):
        self.user = self.scope.get("user")
        self.conversation_id = self.scope["url_route"]["kwargs"]["conversation_id"]
        self.room_group_name = f"chat_{self.conversation_id}"

        if not self.user or not self.user.is_authenticated:
            await self.close(code=4001)
            return

        is_participant = await self.check_participant()
        if not is_participant:
            await self.close(code=4003)
            return

        await self.channel_layer.group_add(self.room_group_name, self.channel_name)
        await self.accept()
        await self.set_online(True)

        # Broadcast presence
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                "type": "user.presence",
                "user_id": str(self.user.id),
                "is_online": True,
            },
        )

    async def disconnect(self, close_code):
        if hasattr(self, "room_group_name"):
            await self.channel_layer.group_discard(
                self.room_group_name, self.channel_name
            )
        if hasattr(self, "user") and self.user.is_authenticated:
            await self.set_online(False)
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    "type": "user.presence",
                    "user_id": str(self.user.id),
                    "is_online": False,
                    "last_seen": timezone.now().isoformat(),
                },
            )

    async def receive(self, text_data):
        try:
            data = json.loads(text_data)
        except json.JSONDecodeError:
            await self.send_error("Invalid JSON.")
            return

        event_type = data.get("type")
        handlers = {
            "chat.message": self.handle_message,
            "chat.typing": self.handle_typing,
            "chat.read": self.handle_read,
            "chat.reaction": self.handle_reaction,
            "chat.delete": self.handle_delete,
            "chat.edit": self.handle_edit,
        }
        handler = handlers.get(event_type)
        if handler:
            await handler(data)
        else:
            await self.send_error(f"Unknown event type: {event_type}")

    async def handle_message(self, data):
        content = data.get("content", "").strip()
        message_type = data.get("message_type", "text")
        reply_to_id = data.get("reply_to_id")

        if not content and message_type == "text":
            await self.send_error("Message content is required.")
            return

        message = await self.create_message(content, message_type, reply_to_id)
        serialized = await self.serialize_message(message)

        await self.channel_layer.group_send(
            self.room_group_name,
            {
                "type": "chat.message",
                "message": serialized,
            },
        )

    async def handle_typing(self, data):
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                "type": "chat.typing",
                "user_id": str(self.user.id),
                "username": self.user.username,
                "is_typing": bool(data.get("is_typing", False)),
            },
        )

    async def handle_read(self, data):
        message_id = data.get("message_id")
        if not message_id:
            return
        await self.mark_message_read(message_id)
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                "type": "chat.read",
                "message_id": message_id,
                "user_id": str(self.user.id),
            },
        )

    async def handle_reaction(self, data):
        message_id = data.get("message_id")
        emoji = data.get("emoji", "").strip()
        action = data.get("action", "add")  # 'add' or 'remove'
        if not message_id or not emoji:
            return
        await self.toggle_reaction(message_id, emoji, action)
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                "type": "chat.reaction",
                "message_id": message_id,
                "emoji": emoji,
                "user_id": str(self.user.id),
                "action": action,
            },
        )

    async def handle_delete(self, data):
        message_id = data.get("message_id")
        if not message_id:
            return
        success = await self.delete_message(message_id)
        if success:
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    "type": "chat.delete",
                    "message_id": message_id,
                },
            )

    async def handle_edit(self, data):
        message_id = data.get("message_id")
        new_content = data.get("content", "").strip()
        if not message_id or not new_content:
            return
        success = await self.edit_message(message_id, new_content)
        if success:
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    "type": "chat.edit",
                    "message_id": message_id,
                    "content": new_content,
                },
            )

    async def chat_message(self, event):
        await self.send(
            text_data=json.dumps({"type": "chat.message", "message": event["message"]})
        )

    async def chat_typing(self, event):
        if event["user_id"] != str(self.user.id):
            await self.send(text_data=json.dumps(event))

    async def chat_read(self, event):
        await self.send(text_data=json.dumps(event))

    async def chat_reaction(self, event):
        await self.send(text_data=json.dumps(event))

    async def chat_delete(self, event):
        await self.send(text_data=json.dumps(event))

    async def chat_edit(self, event):
        await self.send(text_data=json.dumps(event))

    async def user_presence(self, event):
        await self.send(text_data=json.dumps(event))

    @database_sync_to_async
    def check_participant(self):
        return Conversation.objects.filter(
            id=self.conversation_id, participants=self.user
        ).exists()

    @database_sync_to_async
    def create_message(self, content, message_type, reply_to_id):
        reply_to = None
        if reply_to_id:
            reply_to = Message.objects.filter(id=reply_to_id).first()
        msg = Message.objects.create(
            conversation_id=self.conversation_id,
            sender=self.user,
            content=content,
            message_type=message_type,
            reply_to=reply_to,
        )
        Conversation.objects.filter(id=self.conversation_id).update(
            updated_at=timezone.now()
        )
        return msg

    @database_sync_to_async
    def serialize_message(self, message):
        # Refresh from DB to get all relations
        message.refresh_from_db()
        return MessageSerializer(message).data

    @database_sync_to_async
    def mark_message_read(self, message_id):
        MessageReadReceipt.objects.get_or_create(message_id=message_id, user=self.user)
        ConversationParticipant.objects.filter(
            conversation_id=self.conversation_id, user=self.user
        ).update(last_read_at=timezone.now())

    @database_sync_to_async
    def toggle_reaction(self, message_id, emoji, action):
        if action == "add":
            from .models import MessageReaction

            MessageReaction.objects.get_or_create(
                message_id=message_id, user=self.user, emoji=emoji
            )
        else:
            from .models import MessageReaction

            MessageReaction.objects.filter(
                message_id=message_id, user=self.user, emoji=emoji
            ).delete()

    @database_sync_to_async
    def delete_message(self, message_id):
        try:
            msg = Message.objects.get(id=message_id, sender=self.user)
            msg.soft_delete()
            return True
        except Message.DoesNotExist:
            return False

    @database_sync_to_async
    def edit_message(self, message_id, content):
        updated = Message.objects.filter(
            id=message_id, sender=self.user, is_deleted=False
        ).update(content=content, is_edited=True, updated_at=timezone.now())
        return updated > 0

    @database_sync_to_async
    def set_online(self, is_online):
        from django.contrib.auth import get_user_model

        User = get_user_model()
        User.objects.filter(id=self.user.id).update(
            is_online=is_online,
            last_seen=timezone.now() if not is_online else None,
        )

    async def send_error(self, message):
        await self.send(text_data=json.dumps({"type": "error", "detail": message}))


class PresenceConsumer(AsyncWebsocketConsumer):

    async def connect(self):
        self.user = self.scope.get("user")
        if not self.user or not self.user.is_authenticated:
            await self.close(code=4001)
            return
        await self.channel_layer.group_add("presence", self.channel_name)
        await self.accept()
        await self.set_online(True)
        await self.channel_layer.group_send(
            "presence",
            {
                "type": "user.presence",
                "user_id": str(self.user.id),
                "username": self.user.username,
                "is_online": True,
            },
        )

    async def disconnect(self, close_code):
        if hasattr(self, "user") and self.user.is_authenticated:
            await self.set_online(False)
            await self.channel_layer.group_send(
                "presence",
                {
                    "type": "user.presence",
                    "user_id": str(self.user.id),
                    "username": self.user.username,
                    "is_online": False,
                    "last_seen": timezone.now().isoformat(),
                },
            )
        await self.channel_layer.group_discard("presence", self.channel_name)

    async def user_presence(self, event):
        await self.send(text_data=json.dumps(event))

    @database_sync_to_async
    def set_online(self, is_online):
        from django.contrib.auth import get_user_model

        User = get_user_model()
        User.objects.filter(id=self.user.id).update(
            is_online=is_online,
            last_seen=timezone.now() if not is_online else None,
        )
