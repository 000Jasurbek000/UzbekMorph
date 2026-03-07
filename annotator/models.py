from __future__ import annotations

from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    ROLE_CHOICES = [
        ("admin", "Admin"),
        ("annotator", "Testlovchi"),
    ]

    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default="annotator")
    total_annotations = models.IntegerField(default=0)
    today_annotations = models.IntegerField(default=0)
    last_activity = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["username"]

    def __str__(self) -> str:
        return self.username


class DatasetConfig(models.Model):
    MODE_CHOICES = [
        ("shared", "Umumiy (barcha uchun bir xil)"),
        ("individual", "Individual (har userga alohida)"),
    ]

    name = models.CharField(max_length=200)
    assignment_mode = models.CharField(max_length=20, choices=MODE_CHOICES, default="individual")
    tokens_file = models.FileField(upload_to="datasets/tokens/")
    suffix_file = models.FileField(upload_to="datasets/suffixes/")
    is_active = models.BooleanField(default=False)
    token_count = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if self.is_active:
            DatasetConfig.objects.exclude(pk=self.pk).update(is_active=False)

    def __str__(self) -> str:
        return f"{self.name} ({self.assignment_mode})"


class TokenAssignment(models.Model):
    dataset = models.ForeignKey(DatasetConfig, on_delete=models.CASCADE, related_name="assignments", null=True, blank=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="assignments")
    token_index = models.IntegerField()
    word = models.CharField(max_length=255)
    mode = models.CharField(max_length=20, choices=DatasetConfig.MODE_CHOICES, default="individual")
    assigned_at = models.DateTimeField(auto_now_add=True)
    is_completed = models.BooleanField(default=False)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["token_index"]
        unique_together = [("dataset", "user", "token_index", "mode")]

    def __str__(self) -> str:
        return f"{self.user.username}:{self.token_index}:{self.word}"


class Annotation(models.Model):
    ACTION_CHOICES = [
        ("save", "save"),
        ("delete", "delete"),
        ("update", "update"),
    ]

    dataset = models.ForeignKey(DatasetConfig, on_delete=models.CASCADE, related_name="annotations", null=True, blank=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="annotations")
    token_index = models.IntegerField(db_index=True)
    word = models.CharField(max_length=255)
    action = models.CharField(max_length=10, choices=ACTION_CHOICES)
    strategy = models.CharField(max_length=20, default="primary")
    segments = models.JSONField(default=list)
    tags = models.JSONField(default=list)
    subtypes = models.JSONField(default=list)
    codes = models.JSONField(default=list)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.user.username}:{self.token_index}:{self.word}:{self.action}"
