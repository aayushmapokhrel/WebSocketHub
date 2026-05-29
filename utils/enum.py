from django.db import models
from django.db.models import TextChoices


class TypeChoices(TextChoices):
    Direct = "Direct", "Direct"
    Group = "Group", "Group"


class RoleChoices(TextChoices):
    Member = "Member", "Member"
    Admin = "Admin", "Admin"


class MessageTypeChoices(TextChoices):
    Text = "Text", "Text"
    Image = "Image", "Image"
    File = "File", "File"
    Audio = "Audio", "Audio"
    Video = "Video", "Video"
    System = "System", "System"
