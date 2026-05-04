from django_filters import rest_framework as filters
from .models import Application

class ApplicationFilter(filters.FilterSet):
    class Meta:
        model = Application
        fields = {
            'region': ['exact'],
            'position': ['exact'],
            'status': ['exact'],
            'is_student': ['exact'],
            'created_at': ['date', 'date__gte', 'date__lte'],
        }
