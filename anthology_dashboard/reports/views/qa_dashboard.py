from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse, HttpResponseForbidden
from django.views.decorators.http import require_GET, require_POST
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.contrib.auth.models import Group

from reports.models import DraftReport, Approval, MailInstruction, AccessLog
from reports.helpers import ldap_utils, azure_utils


# ---------------------------
# Role Handling Helpers
# ---------------------------

def get_role_from_groups(user):
    """
    Map Django user groups to role codes.
    Admin -> 1
    QA Approver -> 2
    Viewer -> 3
    """
    if not user.is_authenticated:
        return 0
    if user.is_superuser:
        return 1
    groups = user.groups.values_list("name", flat=True)
    if "Admin" in groups:
        return 1
    elif "QA Approver" in groups or "Approver" in groups:
        return 2
    elif "Viewer" in groups:
        return 3
    return 0


def session_role(request):
    """
    Get user role from session or derive from Django groups.
    """
    if request.session.get("USER_ROLE"):
        return request.session["USER_ROLE"]
    role = get_role_from_groups(request.user)
    request.session["USER_ROLE"] = role
    return role


def _log_access(user_id, role, action, subject, request):
    """
    Log user access for audit.
    """
    ip = request.META.get("HTTP_X_FORWARDED_FOR", request.META.get("REMOTE_ADDR"))
    AccessLog.objects.create(
        user_id=user_id,
        role=str(role),
        action=action,
        subject=subject,
        ip_address=ip,
    )


# ---------------------------
# Views
# ---------------------------

@login_required(login_url="/accounts/login/")
@require_GET
def qa_dashboard(request):
    """
    QA Dashboard: Lists all pending draft reports for approver/admin.
    URL: /qa/dashboard/
    """
    role = session_role(request)
    if role not in (1, 2):
        return HttpResponseForbidden("Only Admin and QA Approver can access QA Dashboard.")

    drafts_qs = DraftReport.objects.filter(locked=False).order_by("-created_on")
    page_num = int(request.GET.get("page", 1))
    page_size = int(request.GET.get("page_size", 25))
    paginator = Paginator(drafts_qs, page_size)
    page = paginator.get_page(page_num)

    context = {
        "drafts": page.object_list,
        "page_obj": page,
        "paginator": paginator,
        "user_display": request.user.get_full_name() or request.user.username,
    }

    _log_access(request.user.username, role, "View", "drafts:list", request)
    return render(request, "qa/qa_dashboard.html", context)


@login_required(login_url="/accounts/login/")
@require_GET
def draft_detail(request, draft_id):
    """
    Show draft report details + embedded PDF + recipient lists.
    URL: /qa/draft/<draft_id>/
    """
    role = session_role(request)
    if role not in (1, 2):
        return HttpResponseForbidden("Only Admin and QA Approver can view drafts.")

    draft = get_object_or_404(DraftReport, pk=draft_id)
    pdf_url = azure_utils.get_blob_url(report_type="draft", filename=draft.filename)
    site_members = ldap_utils.get_site_members(draft.site) or []
    region_members = ldap_utils.get_region_members(draft.region) or []
    manual_recipients = list(draft.mail_instructions.values_list("recipient", flat=True))

    context = {
        "draft": draft,
        "pdf_url": pdf_url,
        "site_members": site_members,
        "region_members": region_members,
        "manual_recipients": manual_recipients,
    }

    _log_access(request.user.username, role, "View", f"draft:{draft.id}", request)
    return render(request, "qa/draft_detail.html", context)


@login_required(login_url="/accounts/login/")
@require_GET
def get_recipients(request, site, region):
    """
    Return recipient list for a site/region in JSON.
    URL: /qa/recipients/<site>/<region>/
    """
    role = session_role(request)
    if role not in (1, 2):
        return HttpResponseForbidden("Only Admin and QA Approver can fetch recipients.")

    site_members = ldap_utils.get_site_members(site) or []
    region_members = ldap_utils.get_region_members(region) or []
    recipients = list(dict.fromkeys(site_members + region_members))  # dedupe

    return JsonResponse({"recipients": recipients})


@login_required(login_url="/accounts/login/")
@require_POST
def approve_draft(request, draft_id):
    """
    Approve or mark a draft as Fail.
    URL: /qa/approve/<draft_id>/
    POST params:
      - decision: "pass" or "fail"
      - manual_emails[]: optional list of manual email strings
    """
    role = session_role(request)
    if role != 2:
        return HttpResponseForbidden("Only QA Approver can approve.")

    draft = get_object_or_404(DraftReport, pk=draft_id)
    if draft.locked:
        return JsonResponse({"error": "Draft already approved/locked."}, status=400)

    decision = request.POST.get("decision")
    if decision not in ("pass", "fail"):
        return JsonResponse({"error": "Invalid decision"}, status=400)

    manual_emails = request.POST.getlist("manual_emails[]") or []
    recipients = ldap_utils.get_site_members(draft.site) or []

    if decision == "fail":
        recipients += ldap_utils.get_region_members(draft.region) or []
    recipients += manual_emails
    recipients = [r for r in dict.fromkeys(recipients) if r and "@" in r]

    approval, created = Approval.objects.get_or_create(draft=draft)
    approval.approve(
        user_id=request.user.username,
        passed=(decision == "pass"),
        recipients=recipients,
    )

    MailInstruction.objects.bulk_create([
        MailInstruction(
            draft=draft,
            recipient=r,
            source_type=("Custom" if r in manual_emails else "LDAP"),
            added_by=request.user.username,
        )
        for r in recipients
    ])

    _log_access(request.user.username, role, "Approved", f"{draft.id}:{decision}", request)
    return JsonResponse({"ok": True, "recipients_count": len(recipients)})
