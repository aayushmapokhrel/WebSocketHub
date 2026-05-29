from django.urls import path
from .views import (
    ConversationListCreateView,
    ConversationDetailView,
    AddParticipantsView,
    RemoveParticipantView,
    MuteConversationView,
    ArchiveConversationView,
    MarkReadView,
    MessageListCreateView,
    MessageDetailView,
    MessageSearchView,
    MessageReactionView,
    MessageReadReceiptView,
)

urlpatterns = [
    # Conversations
    path(
        "conversations/",
        ConversationListCreateView.as_view(),
        name="conversation-list-create",
    ),
    path(
        "conversations/<uuid:pk>/",
        ConversationDetailView.as_view(),
        name="conversation-detail",
    ),
    path(
        "conversations/<uuid:pk>/participants/add/",
        AddParticipantsView.as_view(),
        name="conversation-add-participants",
    ),
    path(
        "conversations/<uuid:pk>/participants/<uuid:uid>/",
        RemoveParticipantView.as_view(),
        name="conversation-remove-participant",
    ),
    path(
        "conversations/<uuid:pk>/mute/",
        MuteConversationView.as_view(),
        name="conversation-mute",
    ),
    path(
        "conversations/<uuid:pk>/archive/",
        ArchiveConversationView.as_view(),
        name="conversation-archive",
    ),
    path(
        "conversations/<uuid:pk>/read/",
        MarkReadView.as_view(),
        name="conversation-mark-read",
    ),
    # Messages
    path(
        "conversations/<uuid:pk>/messages/",
        MessageListCreateView.as_view(),
        name="message-list-create",
    ),
    path(
        "conversations/<uuid:pk>/messages/search/",
        MessageSearchView.as_view(),
        name="message-search",
    ),
    path("messages/<uuid:pk>/", MessageDetailView.as_view(), name="message-detail"),
    path(
        "messages/<uuid:pk>/reactions/",
        MessageReactionView.as_view(),
        name="message-reactions",
    ),
    path(
        "messages/<uuid:pk>/read/",
        MessageReadReceiptView.as_view(),
        name="message-read-receipt",
    ),
]
