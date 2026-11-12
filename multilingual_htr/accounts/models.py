from django.db import models
from django.contrib.auth.models import User


class UserProfile(models.Model):
    """Extended user profile storing preferences and metadata."""
    LANGUAGE_CHOICES = [
        ('en', 'English'),
        ('te', 'Telugu (తెలుగు)'),
        ('hi', 'Hindi (हिन्दी)'),
        ('ta', 'Tamil (தமிழ்)'),
        ('kn', 'Kannada (ಕನ್ನಡ)'),
        ('mr', 'Marathi (मराठी)'),
        ('bn', 'Bengali (বাংলা)'),
    ]

    ENGINE_CHOICES = [
        ('easyocr', 'EasyOCR (Local Deep Learning)'),
        ('trocr', 'TrOCR (Transformer Handwriting)'),
        ('google_vision', 'Google Cloud Vision (Cloud)'),
    ]

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    organization = models.CharField(max_length=150, blank=True)
    preferred_language = models.CharField(max_length=16, choices=LANGUAGE_CHOICES, default='en')
    preferred_engine = models.CharField(max_length=32, choices=ENGINE_CHOICES, default='easyocr')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Profile for {self.user.username}"
