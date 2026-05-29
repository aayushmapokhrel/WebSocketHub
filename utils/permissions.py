from rest_framework.permissions import BasePermission
from chat.models import ConversationParticipant


class IsConversationParticipant(BasePermission):

    message = "You are not a participant of this conversation."

    def has_object_permission(self, request, view, obj):
        conversation = obj if hasattr(obj, "participants") else obj.conversation
        return conversation.participants.filter(id=request.user.id).exists()


class IsConversationAdmin(BasePermission):

    message = "You must be an admin to perform this action."

    def has_object_permission(self, request, view, obj):
        conversation = obj if hasattr(obj, "participants") else obj.conversation
        return ConversationParticipant.objects.filter(
            conversation=conversation, user=request.user, role="admin"
        ).exists()


class IsMessageSender(BasePermission):

    message = "You can only modify your own messages."

    def has_object_permission(self, request, view, obj):
        return obj.sender == request.user
