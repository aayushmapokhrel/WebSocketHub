from rest_framework import serializers
from django.contrib.auth import get_user_model
from chat.models import (
    Conversation,
    ConversationParticipant,
    Message,
    MessageReaction,
    MessageReadReceipt,
)
from accounts.serializers import UserPublicSerializer
from utils.enum import TypeChoices

User = get_user_model()


class MessageReactionSerializer(serializers.ModelSerializer):
    user = UserPublicSerializer(read_only=True)

    class Meta:
        model = MessageReaction
        fields = ["id", "user", "emoji", "created_at"]
        read_only_fields = ["id", "user", "created_at"]


class MessageReadReceiptSerializer(serializers.ModelSerializer):
    user = UserPublicSerializer(read_only=True)

    class Meta:
        model = MessageReadReceipt
        fields = ["user", "read_at"]


class ReplyToSerializer(serializers.ModelSerializer):
    """Lightweight nested message for reply previews."""

    sender = UserPublicSerializer(read_only=True)

    class Meta:
        model = Message
        fields = ["id", "sender", "content", "message_type", "created_at"]


class MessageSerializer(serializers.ModelSerializer):
    sender = UserPublicSerializer(read_only=True)
    reactions = MessageReactionSerializer(many=True, read_only=True)
    reply_to = ReplyToSerializer(read_only=True)
    reply_to_id = serializers.UUIDField(
        write_only=True, required=False, allow_null=True
    )
    read_receipts = MessageReadReceiptSerializer(many=True, read_only=True)

    class Meta:
        model = Message
        fields = [
            "id",
            "conversation",
            "sender",
            "message_type",
            "content",
            "file",
            "reply_to",
            "reply_to_id",
            "is_edited",
            "is_deleted",
            "reactions",
            "read_receipts",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "conversation",
            "sender",
            "is_edited",
            "is_deleted",
            "created_at",
            "updated_at",
        ]

    def validate_reply_to_id(self, value):
        if value and not Message.objects.filter(id=value).exists():
            raise serializers.ValidationError("Reply target does not exist.")
        return value


class ConversationParticipantSerializer(serializers.ModelSerializer):
    user = UserPublicSerializer(read_only=True)
    unread_count = serializers.ReadOnlyField()

    class Meta:
        model = ConversationParticipant
        fields = [
            "id",
            "user",
            "role",
            "is_muted",
            "is_archived",
            "unread_count",
            "last_read_at",
            "joined_at",
        ]
        read_only_fields = ["id", "user", "joined_at"]


class ConversationSerializer(serializers.ModelSerializer):
    participants = ConversationParticipantSerializer(
        source="memberships", many=True, read_only=True
    )
    last_message = MessageSerializer(read_only=True)
    created_by = UserPublicSerializer(read_only=True)
    participant_ids = serializers.ListField(
        child=serializers.UUIDField(), write_only=True, required=False
    )

    class Meta:
        model = Conversation
        fields = [
            "id",
            "type",
            "name",
            "avatar",
            "description",
            "created_by",
            "participants",
            "participant_ids",
            "last_message",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_by", "created_at", "updated_at"]

    def validate(self, attrs):
        conv_type = attrs.get("type", TypeChoices.Direct)
        if conv_type == TypeChoices.Group and not attrs.get("name", "").strip():
            raise serializers.ValidationError(
                {"name": "Group conversations require a name."}
            )

        return attrs

    def create(self, validated_data):
        participant_ids = validated_data.pop("participant_ids", [])
        request = self.context["request"]
        user = request.user

        # For direct chats, enforce uniqueness
        if validated_data.get("type") == TypeChoices.Direct:
            if len(participant_ids) != 1:
                raise serializers.ValidationError(
                    "Direct conversations require exactly one other participant."
                )
            other_id = participant_ids[0]
            existing = (
                Conversation.objects.filter(
                    type=TypeChoices.Direct,
                    participants=user,
                )
                .filter(participants__id=other_id)
                .first()
            )
            if existing:
                return existing

        conversation = Conversation.objects.create(created_by=user, **validated_data)
        ConversationParticipant.objects.create(
            conversation=conversation, user=user, role="admin"
        )
        for pid in participant_ids:
            try:
                other = User.objects.get(id=pid)
                ConversationParticipant.objects.get_or_create(
                    conversation=conversation, user=other
                )
            except User.DoesNotExist:
                pass
        return conversation


class AddParticipantsSerializer(serializers.Serializer):
    user_ids = serializers.ListField(child=serializers.UUIDField(), min_length=1)


class UpdateConversationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Conversation
        fields = ["name", "description", "avatar"]
