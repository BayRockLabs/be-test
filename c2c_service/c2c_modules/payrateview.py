from drf_yasg.utils import swagger_auto_schema
from rest_framework.response import Response
from rest_framework import generics
from rest_framework.pagination import PageNumberPagination
from c2c_modules.models import SkillPayRate
from c2c_modules.serializer import SkillPayRateSerializer
from c2c_modules.utils import has_permission
#   ================================================================
class Pagination(PageNumberPagination):
    page_size = 10
    page_size_query_param = 'page_size'
    max_page_size = 1000

class SkillPayRateAPIView(generics.ListAPIView):
    serializer_class = SkillPayRateSerializer

    def get_queryset(self):
        queryset = SkillPayRate.objects.all()
        return queryset

    @swagger_auto_schema(tags=["Payrate"])
    def get(self, request,*args, **kwargs):
        required_roles = ["c2c_skillpayrate_admin","c2c_skillpayrate_viewer","c2c_viewer","c2c_super_admin","c2c_est_admin","c2c_pricing_admin"]
        result = has_permission(request, required_roles)
        if result["status"] == 200:
            data = dict()
            response = self.list(request, *args, **kwargs)
            data['result'] = response.data
            data.update({"roles_response": result})
            return Response(data)
        else:
            return Response({"roles_response": result})
