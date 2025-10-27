import pytest
from django.urls import reverse
from django.test import Client
from reports.models import DraftReport, Approval, MailInstruction

@pytest.fixture
def client():
    return Client()

@pytest.fixture
def draft(db):
    return DraftReport.objects.create(filename="drafts/report_x.pdf", site="SiteA", region="Region1", study_id="STUDY-1")

def test_qa_dashboard_and_approve(monkeypatch, client, draft):
    # monkeypatch ldap and azure helpers
    from django.conf import settings
    settings.MOCK_LDAP = {
        "site_members": {"SiteA": ["site.user@company.com"]},
        "region_members": {"Region1": ["region.user@company.com"]},
    }
    # mock azure URL construction (not necessary but safe)
    monkeypatch.setenv("AZ_STORAGE_HOSTNAME", "")
    # simulate SSO mock login: set session keys
    session = client.session
    session["USER_ID"] = "approver.user"
    session["USER_DISPLAY_NAME"] = "Approver User"
    session["USER_ROLE"] = 2  # approver
    session.save()

    # access dashboard
    resp = client.get(reverse("qa:dashboard"))
    assert resp.status_code == 200
    # view draft detail
    resp = client.get(reverse("qa:draft_detail", args=[draft.id]))
    assert resp.status_code == 200
    # approve draft (pass)
    url = reverse("qa:approve_draft", args=[draft.id])
    resp = client.post(url, {"decision": "pass"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    # DB assertions
    approval = Approval.objects.get(draft=draft)
    assert approval.passed is True
    # MailInstruction created
    mails = MailInstruction.objects.filter(draft=draft)
    assert mails.count() >= 1
