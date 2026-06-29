from django.shortcuts import render


def home(request):
    return render(request, "money_manager/home.html")
