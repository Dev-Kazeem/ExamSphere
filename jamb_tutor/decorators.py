from django.shortcuts import redirect
from functools import wraps
def jamb_only(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated or not hasattr(request.user, 'jambprofile'):
            return redirect('university_dashboard' if hasattr(request.user, 'id') else 'login')
        return view_func(request, *args, **kwargs)
    return wrapper