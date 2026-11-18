# whatsapp_urls.py
from django.urls import path
from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
import json, os
from .whatsapp import handle_whatsapp
VERIFY = os.getenv("WHATSAPP_VERIFY_TOKEN","jamb123")
@csrf_exempt
def webhook(request):
    if request.method=='GET':
        if request.GET.get('hub.verify_token')==VERIFY:
            return HttpResponse(request.GET.get('hub.challenge'))
        return HttpResponse("Wrong token", status=403)
    if request.method=='POST':
        try:
            data=json.loads(request.body)
            entry=data['entry'][0]['changes'][0]['value']
            if 'messages' in entry:
                msg=entry['messages'][0]
                phone=msg['from']; text=msg['text']['body']; name=entry['contacts'][0]['profile']['name']
                handle_whatsapp(phone, text, name)
        except Exception as e: print(e)
        return JsonResponse({'status':'ok'})
    return HttpResponse("ok")
urlpatterns=[path('webhook/', webhook, name='whatsapp_webhook')]