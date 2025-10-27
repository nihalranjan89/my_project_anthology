from django.conf import settings
from urllib.parse import quote_plus

def get_blob_url(report_type: str, filename: str):
    """
    Build a URL to the Azure blob with SAS token.
    report_type: "draft" or "final"
    """
    account_host = getattr(settings, "AZ_STORAGE_HOSTNAME", None)
    if not account_host:
        # For dev we can return a placeholder or file path.
        return settings.STATIC_URL + "pdf_placeholder.pdf"
    container = settings.AZ_STORAGE_DRAFTS_URI if report_type == "draft" else settings.AZ_STORAGE_FINALS_URI
    sas = getattr(settings, "AZ_TOKEN", "")
    # sanitize filename
    fname = quote_plus(filename)
    url = f"https://{account_host}/{container}/{fname}"
    if sas:
        url = f"{url}?{sas}"
    return url
