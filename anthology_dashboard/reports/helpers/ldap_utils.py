"""
LDAP utility helpers.

These are minimal and safe for dev/test. In production:
 - Use LDAPS
 - Use proper service account stored in Secrets (SECRETS.LDAP_USER)
 - Use caching to reduce LDAP load
"""

from django.conf import settings

# For unit tests / local dev we allow monkeypatching these functions.
def get_site_members(site_name):
    """
    Return list of email addresses for site members.
    """
    # In production, implement LDAP query using ldap3 with settings.LDAP_SERVER & credentials.
    # Example placeholder: try to use settings.MOCK_LDAP dict if present, else return empty list.
    mock = getattr(settings, "MOCK_LDAP", None)
    if mock and isinstance(mock, dict):
        return mock.get("site_members", {}).get(site_name, [])
    # fallback: empty
    return []

def get_region_members(region_name):
    """
    Return list of email addresses for region members.
    """
    mock = getattr(settings, "MOCK_LDAP", None)
    if mock and isinstance(mock, dict):
        return mock.get("region_members", {}).get(region_name, [])
    return []
