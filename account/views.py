from django.shortcuts import render
from django.contrib.auth import authenticate, login, logout
from django.shortcuts import redirect
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm


# Create your views here.

def LoginView(request):
    if not request.user.is_authenticated:
        if request.method == 'POST':
            form = AuthenticationForm(request = request, data = request.POST)
            if form.is_valid():
                username = form.cleaned_data.get('username')
                password = form.cleaned_data.get('password')
                user = authenticate(request, username=username, password=password)
                if user is not None:
                    login(request, user)
                    return redirect('/')

        form = AuthenticationForm()
        context = {'form': form}
        return render(request,'auth/login.html', context)
    else:
        return redirect('/')

def LogoutView(request):
    logout(request)
    return render(request,'dashboard.html')

def SignUpView(request):
    if not request.user.is_authenticated:
        if request.method == 'POST':
            form = UserCreationForm(request.POST)
            if form.is_valid():
                form.save()
                return redirect('/')
        form = UserCreationForm()
        context = {"form":form}
        return render(request,'auth/signup.html',context)
    else:
        return redirect('/')