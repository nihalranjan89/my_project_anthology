from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse, HttpResponseForbidden, HttpResponse
from django.views.decorators.http import require_GET, require_POST
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.conf import settings
from django.utils import timezone

from reports.models import DraftReport, Approval, MailInstruction, AccessLog

from reports.helpers import ldap_utils, azure_utils

# Helper to interpret session role (supports numeric codes or strings)
def session_role(request):
    r = request.session.get("USER_ROLE")
    if r is None:
        return 0
    try:
        # handle string like "APPROVER" or numeric
        if isinstance(r, str) and r.isdigit():
            return int(r)
        if isinstance(r, int):
            return r
        s = str(r).strip().lower()
        if s in ("admin", "1"):
            return 1
        if s in ("approver", "approver", "2"):
            return 2
        if s in ("viewer", "3"):
            return 3
    except Exception:
        pass
    return 0

def is_approver(request):
    return session_role(request) == 2

def is_admin(request):
    return session_role(request) == 1

def is_viewer(request):
    return session_role(request) == 3

def _log_access(user_id, role, action, subject, request):
    ip = request.META.get("HTTP_X_FORWARDED_FOR", request.META.get("REMOTE_ADDR"))
    AccessLog.objects.create(user_id=user_id, role=str(role), action=action, subject=subject, ip_address=ip)


#@login_required
@require_GET
def qa_dashboard(request):
    """
    List pending draft reports for approver/admin.
    URL: /qa/dashboard/
    """
    role = session_role(request)
    if role not in (1, 2):
        return HttpResponseForbidden("Only Admin and QA Approver can access QA Dashboard.")
    drafts_qs = DraftReport.objects.filter(locked=False).order_by("-created_on")
    # simple pagination via ?page= and ?page_size=
    page_num = int(request.GET.get("page", 1))
    page_size = int(request.GET.get("page_size", 25))
    paginator = Paginator(drafts_qs, page_size)
    page = paginator.get_page(page_num)
    context = {
        "drafts": page.object_list,
        "page_obj": page,
        "paginator": paginator,
        "user_display": request.session.get("USER_DISPLAY_NAME"),
    }
    # log view
    _log_access(request.session.get("USER_ID", "unknown"), role, "View", "drafts:list", request)
    return render(request, "qa/qa_dashboard.html", context)


#@login_required
@require_GET
def draft_detail(request, draft_id):
    """
    Show draft detail + embedded PDF viewer + recipient list for editing.
    URL: /qa/draft/<draft_id>/
    """
    role = session_role(request)
    if role not in (1, 2):
        return HttpResponseForbidden("Only Admin and QA Approver can view drafts.")
    draft = get_object_or_404(DraftReport, pk=draft_id)
    # fetch PDF URL (SAS token assumed via settings.AZ_TOKEN)
    pdf_url = azure_utils.get_blob_url(report_type="draft", filename=draft.filename)
    # fetch LDAP recipients (site + region)
    site_members = ldap_utils.get_site_members(draft.site) or []
    region_members = ldap_utils.get_region_members(draft.region) or []
    # fetch any existing manual recipients saved earlier
    manual_recipients = list(draft.mail_instructions.values_list("recipient", flat=True))
    context = {
        "draft": draft,
        "pdf_url": pdf_url,
        "site_members": site_members,
        "region_members": region_members,
        "manual_recipients": manual_recipients,
    }
    # log view for this report
    _log_access(request.session.get("USER_ID", "unknown"), role, "View", f"draft:{draft.id}", request)
    return render(request, "qa/draft_detail.html", context)


#@login_required
@require_GET
def get_recipients(request, site, region):
    """
    Return combined recipient list for a site/region (JSON).
    URL: /qa/recipients/<site>/<region>/
    """
    role = session_role(request)
    if role not in (1, 2):
        return HttpResponseForbidden("Only Admin and QA Approver can fetch recipients.")
    site_members = ldap_utils.get_site_members(site) or []
    region_members = ldap_utils.get_region_members(region) or []
    recipients = list(dict.fromkeys(site_members + region_members))  # dedupe preserving order
    return JsonResponse({"recipients": recipients})


#@login_required
@require_POST
def approve_draft(request, draft_id):
    """
    Approve or mark Fail for a draft.
    POST params:
      - decision: "pass" or "fail"
      - manual_emails[]: optional list of manual email strings
    URL: /qa/approve/<draft_id>/
    """
    if not is_approver(request):
        return HttpResponseForbidden("Only QA Approver can approve.")
    draft = get_object_or_404(DraftReport, pk=draft_id)
    if draft.locked:
        return JsonResponse({"error": "Draft already approved/locked."}, status=400)
    decision = request.POST.get("decision")
    if decision not in ("pass", "fail"):
        return JsonResponse({"error": "Invalid decision"}, status=400)
    manual_emails = request.POST.getlist("manual_emails[]") or []
    # Build recipient list according to BRD: Pass => site members only; Fail => site + region
    recipients = []
    recipients += ldap_utils.get_site_members(draft.site) or []
    if decision == "fail":
        recipients += ldap_utils.get_region_members(draft.region) or []
    recipients += manual_emails
    # minimal validation: email-like strings
    recipients = [r for r in dict.fromkeys(recipients) if r and "@" in r]
    # create or update approval
    approval, created = Approval.objects.get_or_create(draft=draft)
    approval.approve(user_id=request.session.get("USER_ID", "unknown"), passed=(decision == "pass"), recipients=recipients)
    # save mail instructions snapshot
    MailInstruction.objects.bulk_create([
        MailInstruction(draft=draft, recipient=r, source_type=("Custom" if r in manual_emails else "LDAP"), added_by=request.session.get("USER_ID"))
        for r in recipients
    ])
    # Log action
    _log_access(request.session.get("USER_ID", "unknown"), session_role(request), "Approved", f"{draft.id}:{decision}", request)
    # Return result
    return JsonResponse({"ok": True, "recipients_count": len(recipients)})
