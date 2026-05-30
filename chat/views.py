from rest_framework import generics, status, permissions
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from django.shortcuts import get_object_or_404
from django.utils import timezone
from chat.models import (
    Conversation,
    ConversationParticipant,
    Message,
    MessageReaction,
    MessageReadReceipt,
)
from chat.serializers import (
    ConversationSerializer,
    UpdateConversationSerializer,
    MessageSerializer,
    MessageReactionSerializer,
    AddParticipantsSerializer,
)
from utils.permissions import (
    IsConversationParticipant,
    IsConversationAdmin,
    IsMessageSender,
)
from rest_framework.permissions import IsAuthenticated


class ConversationListCreateView(generics.ListCreateAPIView):

    serializer_class = ConversationSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return (
            Conversation.objects.filter(participants=self.request.user)
            .prefetch_related("memberships__user", "messages")
            .distinct()
        )

    def perform_create(self, serializer):
        serializer.save()


class ConversationDetailView(generics.RetrieveUpdateDestroyAPIView):
    """GET/PATCH/DELETE /api/chat/conversations/<id>/"""

    serializer_class = ConversationSerializer
    permission_classes = [IsAuthenticated, IsConversationParticipant]

    def get_queryset(self):
        return Conversation.objects.filter(participants=self.request.user)

    def get_serializer_class(self):
        if self.request.method in ["PATCH", "PUT"]:
            return UpdateConversationSerializer
        return ConversationSerializer

    def destroy(self, request, *args, **kwargs):
        conversation = self.get_object()
        # Only group admins can delete the whole conversation
        if conversation.type == Conversation.GROUP:
            membership = ConversationParticipant.objects.filter(
                conversation=conversation, user=request.user, role="admin"
            ).first()
            if not membership:
                return Response(
                    {"detail": "Only admins can delete group conversations."},
                    status=403,
                )
        conversation.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class AddParticipantsView(APIView):

    permission_classes = [IsAuthenticated, IsConversationAdmin]

    def post(self, request, pk):
        conversation = get_object_or_404(Conversation, pk=pk)
        self.check_object_permissions(request, conversation)
        serializer = AddParticipantsSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        added = []
        for uid in serializer.validated_data["user_ids"]:
            from django.contrib.auth import get_user_model

            User = get_user_model()
            try:
                user = User.objects.get(id=uid)
                _, created = ConversationParticipant.objects.get_or_create(
                    conversation=conversation, user=user
                )
                if created:
                    added.append(str(uid))
            except User.DoesNotExist:
                pass
        return Response({"added": added})


class RemoveParticipantView(APIView):

    permission_classes = [permissions.IsAuthenticated]

    def delete(self, request, pk, uid):
        conversation = get_object_or_404(Conversation, pk=pk)
        # Can remove yourself, or admin can remove others
        if str(uid) != str(request.user.id):
            is_admin = ConversationParticipant.objects.filter(
                conversation=conversation, user=request.user, role="admin"
            ).exists()
            if not is_admin:
                return Response(
                    {"detail": "Only admins can remove other participants."}, status=403
                )
        ConversationParticipant.objects.filter(
            conversation=conversation, user_id=uid
        ).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class MuteConversationView(APIView):

    def post(self, request, pk):
        membership = get_object_or_404(
            ConversationParticipant, conversation_id=pk, user=request.user
        )
        membership.is_muted = not membership.is_muted
        membership.save(update_fields=["is_muted"])
        return Response({"is_muted": membership.is_muted})


class ArchiveConversationView(APIView):

    def post(self, request, pk):
        membership = get_object_or_404(
            ConversationParticipant, conversation_id=pk, user=request.user
        )
        membership.is_archived = not membership.is_archived
        membership.save(update_fields=["is_archived"])
        return Response({"is_archived": membership.is_archived})


class MarkReadView(APIView):

    def post(self, request, pk):
        membership = get_object_or_404(
            ConversationParticipant, conversation_id=pk, user=request.user
        )
        membership.last_read_at = timezone.now()
        membership.save(update_fields=["last_read_at"])
        return Response({"detail": "Marked as read."})


class MessageListCreateView(generics.ListCreateAPIView):

    serializer_class = MessageSerializer
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    permission_classes = [permissions.IsAuthenticated, IsConversationParticipant]

    def get_conversation(self):
        return get_object_or_404(
            Conversation.objects.filter(participants=self.request.user),
            pk=self.kwargs["pk"],
        )

    def get_queryset(self):
        conversation = self.get_conversation()
        return (
            Message.objects.filter(conversation=conversation, is_deleted=False)
            .select_related("sender", "reply_to__sender")
            .prefetch_related("reactions__user", "read_receipts__user")
        )

    def get_object(self):
        return self.get_conversation()

    def perform_create(self, serializer):
        conversation = self.get_conversation()
        reply_to_id = serializer.validated_data.pop("reply_to_id", None)
        reply_to = Message.objects.get(id=reply_to_id) if reply_to_id else None
        message = serializer.save(
            sender=self.request.user, conversation=conversation, reply_to=reply_to
        )
        # Update conversation timestamp
        conversation.updated_at = timezone.now()
        conversation.save(update_fields=["updated_at"])


class MessageDetailView(generics.RetrieveUpdateDestroyAPIView):

    serializer_class = MessageSerializer
    permission_classes = [
        permissions.IsAuthenticated,
        IsConversationParticipant,
        IsMessageSender,
    ]

    def get_queryset(self):
        return Message.objects.filter(conversation__participants=self.request.user)

    def perform_update(self, serializer):
        serializer.save(is_edited=True)

    def destroy(self, request, *args, **kwargs):
        message = self.get_object()
        message.soft_delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class MessageSearchView(generics.ListAPIView):

    serializer_class = MessageSerializer

    def get_queryset(self):
        q = self.request.query_params.get("q", "").strip()
        conversation = get_object_or_404(
            Conversation.objects.filter(participants=self.request.user),
            pk=self.kwargs["pk"],
        )
        if not q:
            return Message.objects.none()
        return Message.objects.filter(
            conversation=conversation, content__icontains=q, is_deleted=False
        )


class MessageReactionView(APIView):

    def post(self, request, pk):
        message = get_object_or_404(Message, pk=pk)
        if not message.conversation.participants.filter(id=request.user.id).exists():
            return Response(status=403)
        emoji = request.data.get("emoji", "").strip()
        if not emoji:
            return Response({"detail": "Emoji required."}, status=400)
        reaction, created = MessageReaction.objects.update_or_create(
            message=message, user=request.user, defaults={"emoji": emoji}
        )
        return Response(
            MessageReactionSerializer(reaction).data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )

    def delete(self, request, pk):
        message = get_object_or_404(Message, pk=pk)
        emoji = request.data.get("emoji", "").strip()
        MessageReaction.objects.filter(
            message=message, user=request.user, emoji=emoji
        ).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class MessageReadReceiptView(APIView):

    def post(self, request, pk):
        message = get_object_or_404(Message, pk=pk)
        if not message.conversation.participants.filter(id=request.user.id).exists():
            return Response(status=403)
        MessageReadReceipt.objects.get_or_create(message=message, user=request.user)
        return Response({"detail": "Marked as read."})
