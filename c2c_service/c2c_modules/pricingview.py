from drf_yasg.utils import swagger_auto_schema
from rest_framework.generics import GenericAPIView
from rest_framework.mixins import ListModelMixin, CreateModelMixin,  DestroyModelMixin, UpdateModelMixin, RetrieveModelMixin
from rest_framework.response import Response
from rest_framework.pagination import PageNumberPagination
from rest_framework import status
from c2c_modules.models import Pricing
from c2c_modules.serializer import PricingSerializer
from c2c_modules.utils import has_permission

class Pagination(PageNumberPagination):
    page_size = 10
    page_size_query_param = 'page_size'
    max_page_size = 1000
class PricingGetAPIView(ListModelMixin, CreateModelMixin, GenericAPIView):
    serializer_class = PricingSerializer
    pagination_class = Pagination

    def get_queryset(self):
        return Pricing.objects.filter(client=self.kwargs['client']).order_by('pricing_creation_date')

    @swagger_auto_schema(tags=["Pricing"])
    def get(self, request, client, *args, **kwargs):
        required_roles = ["c2c_pricing_admin","c2c_pricing_viewer","c2c_viewer","c2c_super_admin","c2c_sow_admin"]
        result = has_permission(request, required_roles)
        if result["status"] == 200:
            response = self.list(request, *args, **kwargs)
            response.data.update({"roles_response": result})
            return response
        else:
            return Response({"roles_response": result})

class PricingPostAPIView(ListModelMixin, CreateModelMixin, GenericAPIView):
    queryset = Pricing.objects.all()  # Add order_by here
    lookup_field = 'uuid'
    pagination_class = Pagination
    serializer_class = PricingSerializer

    @swagger_auto_schema(tags=["Pricing"])
    def get(self, request, *args, **kwargs):
        """List of pricings"""
        required_roles = ["c2c_pricing_admin","c2c_pricing_viewer","c2c_super_admin"]
        result = has_permission(request,required_roles)
        if result["status"] == 200:
            response = self.list(request, *args, **kwargs)
            response.data.update({"result":result})
            return response
        else:
            return Response({"result":result})

    @swagger_auto_schema(tags=["Pricing"])
    def post(self, request, *args, **kwargs):
        """ Create pricings """
        required_roles = ["c2c_pricing_admin","c2c_super_admin"]
        result = has_permission(request,required_roles)
        if result["status"] == 200:
            username = result['username']
            request_data = request.data.copy()
            request_data['username_created'] = username
            request_data['username_updated'] = username
            serializer = self.get_serializer(data=request_data)
            serializer.is_valid(raise_exception=True)
            self.perform_create(serializer)
            response = Response(serializer.data, status=status.HTTP_201_CREATED)
            response.data.update({"result": result})
            return response
        else:
            return Response({"result":result})


class PricingDetailAPIView(RetrieveModelMixin, UpdateModelMixin, DestroyModelMixin, GenericAPIView):
    queryset = Pricing.objects.all().order_by('-pricing_creation_date')
    lookup_field = 'uuid'
    serializer_class = PricingSerializer
    pagination_class = Pagination

    @swagger_auto_schema(tags=["Pricing"])
    def get(self, request, *args, **kwargs):
        """ Retrieve a pricing """
        required_roles = ["c2c_pricing_admin","c2c_pricing_viewer","c2c_viewer","c2c_super_admin"]
        result = has_permission(request,required_roles)
        if result["status"] == 200:
            response = self.retrieve(request, *args, **kwargs)
            response.data.update({"result":result})
            return response
        else:
            return Response({"result":result})


    @swagger_auto_schema(tags=["Pricing"])
    def patch(self, request, *args, **kwargs):
        """ Partially update a pricing """
        required_roles = ["c2c_pricing_admin","c2c_super_admin"]
        result = has_permission(request,required_roles)
        if result["status"] == 200:
            username = result['username']
            instance = self.get_object()
            request_data = request.data.copy()
            request_data['username_updated'] = username
            serializer = self.get_serializer(instance, data=request_data, partial=True)
            serializer.is_valid(raise_exception=True)
            self.perform_update(serializer)
            data = serializer.data
            data.update({"result": result})
            return Response({"result": data}, status=status.HTTP_200_OK)
        else:
            return Response({"result":result})

    @swagger_auto_schema(tags=["Pricing"])
    def delete(self, request, *args, **kwargs):
        """ Delete a pricing """
        required_roles = ["c2c_pricing_admin","c2c_super_admin"]
        result = has_permission(request,required_roles)
        if result["status"] == 200:
            instance = self.get_object()
            self.perform_destroy(instance)
            return Response({"message": "Pricing deleted successfully","result":result})
        else:
            return Response({"result":result})
