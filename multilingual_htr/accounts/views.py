from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.views import LoginView as BaseLoginView, PasswordChangeView
from django.contrib.auth.decorators import login_required
from django.urls import reverse_lazy
from django.views import View

from .forms import (
    UserRegistrationForm,
    UserLoginForm,
    UserUpdateForm,
    ProfileUpdateForm,
    StyledPasswordChangeForm,
)
from .models import UserProfile


class RegisterView(View):
    def get(self, request):
        if request.user.is_authenticated:
            return redirect('dashboard:index')
        form = UserRegistrationForm()
        return render(request, 'accounts/register.html', {'form': form})

    def post(self, request):
        if request.user.is_authenticated:
            return redirect('dashboard:index')
        form = UserRegistrationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(request, f"Welcome to Multilingual HTR, {user.username}! Your account has been created.")
            return redirect('dashboard:index')
        return render(request, 'accounts/register.html', {'form': form})


class LoginView(BaseLoginView):
    form_class = UserLoginForm
    template_name = 'accounts/login.html'
    redirect_authenticated_user = True

    def form_valid(self, form):
        messages.success(self.request, f"Welcome back, {form.get_user().username}!")
        return super().form_valid(form)


class LogoutView(View):
    def post(self, request):
        logout(request)
        messages.info(request, "You have been logged out successfully.")
        return redirect('home')

    def get(self, request):
        logout(request)
        messages.info(request, "You have been logged out successfully.")
        return redirect('home')


@login_required
def profile_view(request):
    # Ensure profile exists
    profile, _ = UserProfile.objects.get_or_create(user=request.user)
    
    if request.method == 'POST':
        u_form = UserUpdateForm(request.POST, instance=request.user)
        p_form = ProfileUpdateForm(request.POST, instance=profile)
        if u_form.is_valid() and p_form.is_valid():
            u_form.save()
            p_form.save()
            messages.success(request, "Your profile settings have been updated successfully.")
            return redirect('accounts:profile')
    else:
        u_form = UserUpdateForm(instance=request.user)
        p_form = ProfileUpdateForm(instance=profile)

    context = {
        'u_form': u_form,
        'p_form': p_form,
        'profile': profile,
    }
    return render(request, 'accounts/profile.html', context)


class CustomPasswordChangeView(PasswordChangeView):
    form_class = StyledPasswordChangeForm
    template_name = 'accounts/password_change.html'
    success_url = reverse_lazy('accounts:profile')

    def form_valid(self, form):
        messages.success(self.request, "Your password was changed successfully.")
        return super().form_valid(form)
