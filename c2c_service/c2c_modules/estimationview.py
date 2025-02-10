from drf_yasg.utils import swagger_auto_schema
from django.utils.dateparse import parse_date
from rest_framework.generics import GenericAPIView
from rest_framework.mixins import ListModelMixin, CreateModelMixin,  DestroyModelMixin, UpdateModelMixin, RetrieveModelMixin
from rest_framework.response import Response
from rest_framework.pagination import PageNumberPagination
from rest_framework import status
from c2c_modules.models import Estimation, SowContract
from c2c_modules.serializer import EstimationSerializer, EstimationUpdateSerializer
from c2c_modules.utils import has_permission
from collections import defaultdict
from datetime import datetime
#   ================================================================
class Pagination(PageNumberPagination):
    page_size = 10
    page_size_query_param = 'page_size'
    max_page_size = 1000

def identify_date_format(estimation_data):
    """Identify the date format based on the highest values in the day and month lists."""
    list1 = []
    list2 = []
    for entry in estimation_data.get("daily", []):
        if "date" in entry:
            date_str = entry["date"]
            parts = date_str.split('/')
            if len(parts) != 3:
                raise ValueError(f"Invalid date format: {date_str}")
            list1.append(int(parts[0]))
            list2.append(int(parts[1]))
    if any(month > 12 for month in list2):
        return "%m/%d/%Y"
    elif any(day > 12 for day in list1):
        return "%d/%m/%Y"
    else:
        return "%d/%m/%Y"

def normalize_dates(estimation_data):
    """Normalize all dates in Estimation_Data['daily'] to a consistent format."""
    if "daily" not in estimation_data:
        raise ValueError("Estimation_Data does not contain 'daily' key.")
    detected_format = identify_date_format(estimation_data)
    for entry in estimation_data["daily"]:
        if "date" in entry:
            date_str = entry["date"]
            try:
                parsed_date = datetime.strptime(date_str, detected_format)
                entry["date"] = parsed_date.strftime("%d/%m/%Y")
            except ValueError as e:
                raise ValueError(f"Error processing date: {date_str} -> {str(e)}")
    return estimation_data

class EstimationPostAPIView(ListModelMixin, CreateModelMixin, GenericAPIView):
    queryset = Estimation.objects.all().order_by('-date_created')
    serializer_class = EstimationSerializer
    pagination_class = Pagination
    lookup_field = 'uuid'

    def get_serializer_class(self):
        return EstimationSerializer

    @swagger_auto_schema(tags=["Estimation"])
    def get(self, request, *args, **kwargs):
        """List of estimations"""
        required_roles = ["c2c_est_admin","c2c_est_viewer","c2c_super_admin"]
        result = has_permission(request,required_roles)
        if result["status"] == 200:
            response = self.list(request, *args, **kwargs)
            response.data.update({"result":result})
            return response
        else:
            return Response({"result":result})

    @swagger_auto_schema(tags=["Estimation"])
    def post(self, request, *args, **kwargs):
        """Create estimations with normalized date formats."""
        required_roles = ["c2c_est_admin", "c2c_super_admin"]
        result = has_permission(request, required_roles)
        if result["status"] == 200:
            username = result['username']
            request_data = request.data.copy()
            for resource in request_data.get('resource', []):
                if 'Estimation_Data' in resource:
                    try:
                        resource['Estimation_Data'] = normalize_dates(resource['Estimation_Data'])
                    except ValueError as e:
                        return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
            request_data['username_created'] = username
            request_data['username_updated'] = username
            serializer = self.get_serializer(data=request_data)
            serializer.is_valid(raise_exception=True)
            self.perform_create(serializer)
            response = Response(serializer.data, status=status.HTTP_201_CREATED)
            response.data.update({"result": result})
            return response
        else:
            return Response({"result": result}, status=status.HTTP_403_FORBIDDEN)


class EstimationGetAPIView(ListModelMixin, CreateModelMixin, GenericAPIView):
    queryset = Estimation.objects.all()
    serializer_class = EstimationSerializer
    pagination_class = Pagination
    lookup_field = 'uuid'

    @swagger_auto_schema(tags=["Estimation"])
    def get(self, request, client, *args, **kwargs):
        required_roles = ["c2c_est_admin","c2c_est_viewer","c2c_viewer","c2c_super_admin","c2c_pricing_admin","c2c_sow_admin"]
        result = has_permission(request,required_roles)
        if result["status"] == 200:
            date_created_str = request.query_params.get('date_created')
            date_created = parse_date(date_created_str) if date_created_str else None
            queryset = self.get_queryset()
            if date_created:
                queryset = queryset.filter(contract_creation_date__gte=date_created)
            if client:
                queryset = queryset.filter(client=client)  # Filter by client_uuid
            queryset = queryset.order_by('-date_created')
            page = self.paginate_queryset(queryset)
            if page is not None:
                serializer = self.get_serializer(page, many=True)
                return self.get_paginated_response(serializer.data)
            serializer_class = self.get_serializer_class()
            serializer = serializer_class(queryset, many=True)
            data = serializer.data
            data.update({"result":result})
            return Response(data, status=status.HTTP_201_CREATED)
        else:
            return Response({"result":result})

class SingleEstimationAPIView(RetrieveModelMixin, UpdateModelMixin, GenericAPIView, DestroyModelMixin):
    queryset = Estimation.objects.all().order_by('-date_created')
    serializer_class = EstimationSerializer
    pagination_class = Pagination
    lookup_field = 'uuid'

    def get_serializer_class(self):
        if self.request.method == 'PATCH':
            return EstimationUpdateSerializer
        return EstimationSerializer

    def is_estimation_linked_to_sow_contract(self, estimation):
        return SowContract.objects.filter(estimation=estimation).exists()

    def calculate_weekly_estimated_hours(self, resource):
        """
        Calculate weekly estimated hours for a single resource, ensuring December dates falling in Week 1 are assigned to the next year.
        """
        report = {}
        num_of_resources = resource.get('num_of_resources', 1)
        weekly_data = resource.get('Estimation_Data', {}).get('weekly', [])
        report['weekly'] = [
            {
                "week": week_entry["week"],
                "hours": week_entry["hours"] * num_of_resources
            }
            for week_entry in weekly_data
        ]
        report['role'] = resource.get('role')
        report['start_date'] = resource.get('start_date')
        report['end_date'] = resource.get('end_date')
        report['num_of_resources'] = num_of_resources
        return report

    @swagger_auto_schema(tags=["Estimation"])
    def get(self, request, *args, **kwargs):
        """Get estimation details."""
        required_roles = ["c2c_est_admin", "c2c_est_viewer", "c2c_viewer", "c2c_super_admin"]
        result = has_permission(request, required_roles)
        if result["status"] != 200:
            return Response({"result": result})
        response = self.retrieve(request, *args, **kwargs)
        if isinstance(response.data, dict) and 'resource' in response.data:
            for resource in response.data['resource']:
                if isinstance(resource, dict):
                    resource['weekly_pdf_estimated_hours'] = self.calculate_weekly_estimated_hours(resource)

        response.data.update({"result": result})
        return response

    @swagger_auto_schema(tags=["Estimation"])
    def put(self, request, *args, **kwargs):
        """ Update estimation details """
        required_roles = ["c2c_est_admin", "c2c_super_admin"]
        result = has_permission(request, required_roles)
        if result["status"] == 200:
            estimation = self.get_object()
            if self.is_estimation_linked_to_sow_contract(estimation):
                return Response(
                    {"message": "PUT operation is not allowed as this estimation was already linked to a Contract SOW"},
                    status=status.HTTP_403_FORBIDDEN
                )
            username = result['username']
            request_data = request.data.copy()
            for resource in request_data.get('resource', []):
                if 'Estimation_Data' in resource:
                    try:
                        resource['Estimation_Data'] = normalize_dates(resource['Estimation_Data'])
                    except ValueError as e:
                        return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
            request_data['username_updated'] = username
            serializer = self.get_serializer(estimation, data=request_data, partial=True)
            serializer.is_valid(raise_exception=True)
            self.perform_update(serializer)
            response = Response(serializer.data)
            response.data.update({"result": result})
            return response
        else:
            return Response({"result": result})


    @swagger_auto_schema(tags=["Estimation"])
    def delete(self, request, *args, **kwargs):
        """Delete an estimation"""
        required_roles = ["c2c_est_admin","c2c_super_admin"]
        result = has_permission(request,required_roles)
        if result["status"] == 200:
            instance = self.get_object()
            self.perform_destroy(instance)
            return Response({"message": "Estimation deleted successfully","result":result})
        else:
            return Response({"result":result})
