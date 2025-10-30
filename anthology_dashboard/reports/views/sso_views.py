import os
from django.shortcuts import redirect, render
from django.http import HttpResponse
from onelogin.saml2.auth import OneLogin_Saml2_Auth
from django.contrib.auth import login
from django.contrib.auth.models import User


def _prepare_django_request(request):
    return {
        'https': 'on' if request.is_secure() else 'off',
        'http_host': request.META.get('HTTP_HOST'),
        'script_name': request.path,
        'get_data': request.GET.copy(),
        'post_data': request.POST.copy(),
    }


def init_saml_auth(request):
    base_path = os.path.join(os.path.dirname(__file__), '../../saml')
    return OneLogin_Saml2_Auth(_prepare_django_request(request), custom_base_path=base_path)


def login_saml(request):
    """Initiate SSO login - redirects to PingFederate IdP"""
    auth = init_saml_auth(request)
    return redirect(auth.login())


def acs(request):
    """Assertion Consumer Service (callback endpoint)"""
    auth = init_saml_auth(request)
    auth.process_response()
    errors = auth.get_errors()
    if errors:
        return HttpResponse(f"❌ SAML Error: {errors}", status=400)

    if not auth.is_authenticated():
        return HttpResponse("❌ SAML Authentication failed.", status=403)

    # Extract user info from SAML attributes
    attrs = auth.get_attributes()
    username = auth.get_nameid() or "unknown_user"
    display_name = attrs.get('cn', [''])[0]
    email = attrs.get('email', [''])[0]

    # Create or update user
    user, _ = User.objects.get_or_create(username=username)
    user.first_name = display_name
    if email:
        user.email = email
    user.save()

    # Log in user
    login(request, user)

    return redirect('/qa/dashboard/')


def metadata(request):
    """Provide SP metadata for IdP registration"""
    base_path = os.path.join(os.path.dirname(__file__), '../../saml')
    auth = OneLogin_Saml2_Auth(_prepare_django_request(request), custom_base_path=base_path)
    metadata = auth.get_settings().get_sp_metadata()
    errors = auth.get_settings().validate_metadata(metadata)
    if len(errors) > 0:
        return HttpResponse(f"Metadata errors: {errors}", status=500)
    return HttpResponse(metadata, content_type='text/xml')
