from django.shortcuts import render


def home(request):
    return render(request, "home.html")


def about(request):
    return render(request, "about.html")


def calendar(request):
    return render(request, "calendar.html")


def tavern(request):
    return render(request, "tavern.html")


def contact(request):
    return render(request, "contact.html")