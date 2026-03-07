from django.contrib.auth.views import LoginView
from django.urls import path

from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("login/", LoginView.as_view(template_name="annotator/login.html"), name="login"),
    path("logout/", views.logout_view, name="logout"),
    path("profile/", views.profile_view, name="profile"),
    path("test/", views.annotate_view, name="annotate"),
    path("statistics/", views.statistics_view, name="statistics"),
    path("admin-panel/", views.admin_dashboard, name="admin_dashboard"),
    path("reset-progress/", views.reset_progress, name="reset_progress"),
    # Token review
    path("tokens/", views.token_review_list, name="token_review_list"),
    path("tokens/<int:token_index>/", views.token_detail, name="token_detail"),
    path("annotations/<int:annotation_id>/edit/", views.annotation_edit, name="annotation_edit"),
    path("annotations/<int:annotation_id>/delete/", views.annotation_delete, name="annotation_delete"),
    # API
    path("api/item", views.api_item, name="api_item"),
    path("api/reanalyze", views.api_reanalyze, name="api_reanalyze"),
    path("api/save", views.api_save, name="api_save"),
    # Export
    path("export/me/<str:fmt>/", views.export_my_results, name="export_my_results"),
    path("export/admin/<str:scope>/<str:fmt>/", views.export_admin_results, name="export_admin_results"),
    path("export/admin/<str:scope>/<str:fmt>/<int:user_id>/", views.export_admin_results, name="export_admin_results_user"),
]
