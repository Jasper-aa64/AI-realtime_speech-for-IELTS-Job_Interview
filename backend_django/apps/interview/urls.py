from django.urls import path

from . import views

urlpatterns = [
    path("questions/", views.questions, name="interview-questions"),
    path("custom-questions/", views.custom_questions, name="interview-custom-questions"),
    path("sessions/", views.sessions, name="interview-sessions"),
    path("sessions/<str:session_id>/", views.session_detail, name="interview-session-detail"),
    path("sessions/<str:session_id>/turns/<str:turn_id>/answer/", views.answer, name="interview-answer"),
    path("sessions/<str:session_id>/turns/<str:turn_id>/skip/", views.skip, name="interview-skip"),
    path("sessions/<str:session_id>/turns/<str:turn_id>/follow-up/", views.follow_up, name="interview-follow-up"),
    path("sessions/<str:session_id>/finish/", views.finish, name="interview-finish"),
    path("sessions/<str:session_id>/abort/", views.abort, name="interview-abort"),
    path("sessions/<str:session_id>/report/", views.report, name="interview-report"),
]
