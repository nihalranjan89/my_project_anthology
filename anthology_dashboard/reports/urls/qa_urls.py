from django.urls import path
from reports.views import qa_dashboard as views

app_name = "qa"

urlpatterns = [
    path("dashboard/", views.qa_dashboard, name="dashboard"),
    path("draft/<int:draft_id>/", views.draft_detail, name="draft_detail"),
    path("recipients/<str:site>/<str:region>/", views.get_recipients, name="get_recipients"),
    path("approve/<int:draft_id>/", views.approve_draft, name="approve_draft"),
]
