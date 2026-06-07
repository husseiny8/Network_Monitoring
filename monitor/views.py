from django.shortcuts import render
from Devices import device
from Connection import *

### Find devices
target_ip = "192.168.1.1/24"
devices = device.scan(target_ip)
###
def dashboard_view(request):
    # Connection test

    #

    return render(request,'dashboard.html',{"devices":devices})

def settings_view(request):
    return render(request,"settings/general.html")


def alerts_view(request):
    return render(request,"alerts/list.html")


def devices_view(request):
    return render(request,"devices/detail.html",{"devices":devices})


def reports_view(request):
    return render(request,"reports/detail.html")
