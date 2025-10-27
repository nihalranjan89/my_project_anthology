from django.db import models
from django.utils import timezone


# 🧾 DraftReport — pending QA approval
class DraftReport(models.Model):
    filename = models.CharField(max_length=255)
    region = models.CharField(max_length=128)
    site = models.CharField(max_length=128)
    study_id = models.CharField(max_length=128, null=True, blank=True)
    batch = models.CharField(max_length=128, null=True, blank=True)
    product = models.CharField(max_length=128, null=True, blank=True)
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    locked = models.BooleanField(default=False)
    created_on = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.study_id or 'Draft'} - {self.filename}"


# ✅ Approval — QA decision (Pass/Fail)
class Approval(models.Model):
    draft = models.OneToOneField(DraftReport, on_delete=models.CASCADE, related_name="approval")
    passed = models.BooleanField(default=False)
    approved_by = models.CharField(max_length=128, blank=True, null=True)
    approved_on = models.DateTimeField(blank=True, null=True)

    def approve(self, user_id, passed, recipients):
        self.passed = passed
        self.approved_by = user_id
        self.approved_on = timezone.now()
        self.save()


# ✉️ MailInstruction — who got emailed
class MailInstruction(models.Model):
    draft = models.ForeignKey(DraftReport, on_delete=models.CASCADE, related_name="mail_instructions")
    recipient = models.EmailField()
    source_type = models.CharField(max_length=16, default="LDAP")  # or Custom
    added_by = models.CharField(max_length=128)
    added_on = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.recipient} ({self.source_type})"


# 🧾 AccessLog — audit trail
class AccessLog(models.Model):
    timestamp = models.DateTimeField(auto_now_add=True)
    user_id = models.CharField(max_length=128)
    role = models.CharField(max_length=32)
    action = models.CharField(max_length=64)
    subject = models.CharField(max_length=256)
    ip_address = models.GenericIPAddressField(null=True, blank=True)

    def __str__(self):
        return f"{self.timestamp} - {self.user_id} - {self.action}"


# 🧠 (Optional) FinalReport — approved report record
class FinalReport(models.Model):
    filename = models.CharField(max_length=255)
    region = models.CharField(max_length=128)
    site = models.CharField(max_length=128)
    study_id = models.CharField(max_length=128, null=True, blank=True)
    batch = models.CharField(max_length=128, null=True, blank=True)
    product = models.CharField(max_length=128, null=True, blank=True)
    passed = models.BooleanField(default=False)
    approved_by = models.CharField(max_length=128)
    approved_on = models.DateTimeField()
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)

    def __str__(self):
        return f"Final: {self.study_id or 'Unknown'}"


# ⚙️ ProcessLog — background task tracking (for Databricks sync, etc.)
class ProcessLog(models.Model):
    timestamp = models.DateTimeField(auto_now_add=True)
    study = models.CharField(max_length=128)
    region = models.CharField(max_length=128)
    site = models.CharField(max_length=128)
    product = models.CharField(max_length=128)
    state = models.CharField(max_length=64)
    text = models.TextField()

    def __str__(self):
        return f"[{self.state}] {self.study}"
