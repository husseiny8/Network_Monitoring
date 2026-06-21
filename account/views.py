from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import PermissionDenied, ValidationError
from django.shortcuts import get_object_or_404, redirect, render


def LoginView(request):
    if not request.user.is_authenticated:
        if request.method == 'POST':
            form = AuthenticationForm(request=request, data=request.POST)
            if form.is_valid():
                username = form.cleaned_data.get('username')
                password = form.cleaned_data.get('password')
                user = authenticate(request, username=username, password=password)
                if user is not None:
                    login(request, user)
                    messages.success(request, "ورود با موفقیت انجام شد.")
                    return redirect('/')

        form = AuthenticationForm()
        context = {'form': form}
        return render(request, 'auth/login.html', context)
    else:
        return redirect('/')


def LogoutView(request):
    logout(request)
    messages.success(request, "از حساب کاربری خود خارج شدید.")
    return redirect('/')


def SignUpView(request):
    if not request.user.is_authenticated:
        if request.method == 'POST':
            form = UserCreationForm(request.POST)
            if form.is_valid():
                # The very first account created on a fresh install becomes
                # an administrator, so there's always someone able to reach
                # the Users page and promote/manage everyone else.
                is_first_user = not User.objects.exists()

                user = form.save()
                if is_first_user:
                    user.is_staff = True
                    user.is_superuser = True
                    user.save()

                login(request, user)
                messages.success(
                    request, f"خوش آمدید {user.username}! حساب شما با موفقیت ایجاد شد."
                )
                return redirect('/')
        form = UserCreationForm()
        context = {"form": form}
        return render(request, 'auth/signup.html', context)
    else:
        return redirect('/')


# --------------------------------------------------------------------------
# Users management (staff only) - backs the "کاربران" sidebar link and the
# templates/users/list.html + form.html pages, which existed with no view
# behind them.
# --------------------------------------------------------------------------

def _role_for(user):
    if user.is_superuser:
        return "Administrator"
    if user.is_staff:
        return "Operator"
    return "Viewer"


def _apply_role(user, role):
    role = (role or "Viewer").strip()
    user.is_superuser = role == "Administrator"
    user.is_staff = role in ("Administrator", "Operator")


def staff_required(view_func):
    @login_required
    def wrapped(request, *args, **kwargs):
        if not request.user.is_staff:
            raise PermissionDenied("Staff access required.")
        return view_func(request, *args, **kwargs)
    return wrapped


@staff_required
def users_view(request):
    users = list(User.objects.all().order_by("username"))
    for u in users:
        u.role = _role_for(u)
    return render(request, "users/list.html", {"users": users})


@staff_required
def user_form_view(request, user_id=None):
    target = get_object_or_404(User, pk=user_id) if user_id else None

    if request.method == "POST":
        username = request.POST.get("username", "").strip()
        email = request.POST.get("email", "").strip()
        role = request.POST.get("role", "Viewer")
        password = request.POST.get("password", "")

        # Carries the submitted values back into the form on a validation
        # error, instead of silently resetting to the pre-edit values.
        form_state = {
            "target": target,
            "submitted": {"username": username, "email": email, "role": role},
        }

        if not username:
            messages.error(request, "نام کاربری الزامی است.")
            return render(request, "users/form.html", form_state)

        is_new = target is None

        if is_new and User.objects.filter(username=username).exists():
            messages.error(request, "این نام کاربری قبلاً استفاده شده است.")
            return render(request, "users/form.html", form_state)

        if is_new and not password:
            messages.error(request, "برای کاربر جدید رمز عبور الزامی است.")
            return render(request, "users/form.html", form_state)

        candidate = target if target else User(username=username)
        candidate.username = username
        candidate.email = email
        _apply_role(candidate, role)

        if password:
            try:
                validate_password(password, candidate)
            except ValidationError as exc:
                for err in exc.messages:
                    messages.error(request, err)
                return render(request, "users/form.html", form_state)
            candidate.set_password(password)

        candidate.save()
        messages.success(request, "کاربر با موفقیت ذخیره شد.")
        return redirect("users")

    context = {"target": target}
    if target:
        context["submitted"] = {
            "username": target.username,
            "email": target.email,
            "role": _role_for(target),
        }
    return render(request, "users/form.html", context)
