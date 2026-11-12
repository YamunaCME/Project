from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import User
from .models import UserProfile

class UserProfileInline(admin.StackedInline):
    model = UserProfile
    can_delete = False
    verbose_name_plural = 'Profile Preferences'

class UserAdmin(BaseUserAdmin):
    inlines = (UserProfileInline,)
    list_display = ('username', 'email', 'first_name', 'last_name', 'is_staff', 'get_preferred_language')

    def get_preferred_language(self, instance):
        if hasattr(instance, 'profile'):
            return instance.profile.get_preferred_language_display()
        return '-'
    get_preferred_language.short_description = 'Working Language'

admin.site.unregister(User)
admin.site.register(User, UserAdmin)
