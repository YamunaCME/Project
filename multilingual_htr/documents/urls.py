from django.urls import path
from . import views

app_name = 'documents'

urlpatterns = [
    path('', views.DocumentListView.as_view(), name='list'),
    path('upload/', views.DocumentUploadView.as_view(), name='upload'),
    path('<int:pk>/', views.DocumentDetailView.as_view(), name='detail'),
    path('<int:pk>/recognize/', views.DocumentRecognizeView.as_view(), name='recognize'),
    path('<int:pk>/results/', views.DocumentResultsView.as_view(), name='results'),
    path('<int:pk>/edit/', views.DocumentEditView.as_view(), name='edit'),
    path('<int:pk>/translate/', views.DocumentTranslateView.as_view(), name='translate'),
    path('<int:pk>/export/pdf/', views.ExportPdfView.as_view(), name='export_pdf'),
    path('<int:pk>/export/docx/', views.ExportDocxView.as_view(), name='export_docx'),
    path('<int:pk>/export/txt/', views.ExportTxtView.as_view(), name='export_txt'),
    path('<int:pk>/export/csv/', views.ExportCsvView.as_view(), name='export_csv'),
    path('<int:pk>/export/translation/txt/', views.ExportTranslationTxtView.as_view(), name='export_trans_txt'),
    path('<int:pk>/delete/', views.DocumentDeleteView.as_view(), name='delete'),
]
