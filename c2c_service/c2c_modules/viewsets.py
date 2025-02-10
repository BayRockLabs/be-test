from .serializer import SkillPayRateSerializer
from .models import SkillPayRate
from rest_framework import viewsets


class PayrateViewSet(viewsets.ReadOnlyModelViewSet):
    """
    A simple ViewSet for viewing accounts.
    """
    queryset = SkillPayRate.objects.all()
    serializer_class = SkillPayRateSerializer
