import os
from django.db.models.signals import post_delete
from django.dispatch import receiver
from .models import Document

@receiver(post_delete, sender=Document)
def delete_document_files(sender, instance, **kwargs):
    """Ensure files are removed from disk when a Document model is deleted."""
    for field in [instance.original_file, instance.processed_file]:
        if field and hasattr(field, 'path') and os.path.exists(field.path):
            try:
                os.remove(field.path)
            except OSError:
                pass
