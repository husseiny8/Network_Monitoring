from django.http import JsonResponse
from django.shortcuts import render

from Connection.ping import ping_and_store
from Devices import device

### Find devices
target_ip = "192.168.1.1/24"
devices = device.scan(target_ip)
###

def ping_api(request):
    ping = ping_and_store("8.8.8.8")
    return JsonResponse(ping)
def dashboard_view(request):
    # Connection test #
    return render(request,'dashboard.html',{"devices":devices} )

def settings_view(request):
    return render(request,"settings/general.html")


def alerts_view(request):
    return render(request,"alerts/list.html")


def devices_view(request):
    return render(request,"devices/detail.html",{"devices":devices})


def reports_view(request):
    return render(request,"reports/detail.html")
