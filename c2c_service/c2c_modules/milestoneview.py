from drf_yasg.utils import swagger_auto_schema
from rest_framework.generics import GenericAPIView
from rest_framework.mixins import ListModelMixin, CreateModelMixin,  DestroyModelMixin, UpdateModelMixin, RetrieveModelMixin
from rest_framework.response import Response
from rest_framework.pagination import PageNumberPagination
from rest_framework import status
from c2c_modules.models import MainMilestone, SowContract
from c2c_modules.serializer import MainMilestoneCreateSerializer, MainMilestoneSerializer, ContractSowSerializer, MilestoneUpdateSerializer
from c2c_modules.utils import has_permission
#   ================================================================
class Pagination(PageNumberPagination):
    page_size = 10
    page_size_query_param = 'page_size'
    max_page_size = 1000
class MilestoneGetAPIView(ListModelMixin, CreateModelMixin, GenericAPIView):
    serializer_class = MainMilestoneSerializer
    pagination_class = Pagination


    def get_queryset(self):
        return MainMilestone.objects.filter(client_uuid=self.kwargs['client_uuid']).order_by('-uuid')

    @swagger_auto_schema(tags=["Milestone"])
    def get(self, request, client_uuid, *args, **kwargs):
        required_roles = ["c2c_milestone_admin","c2c_milestone_viewer","c2c_viewer","c2c_super_admin"]
        result = has_permission(request, required_roles)
        if result["status"] == 200:
            response = self.list(request, *args, **kwargs)
            response.data.update({"roles_response": result})
            return response
        else:
            return Response({"roles_response": result})

class MilestonePostAPIView(ListModelMixin, CreateModelMixin, GenericAPIView):
    queryset = MainMilestone.objects.all()
    serializer_class = MainMilestoneCreateSerializer
    pagination_class = Pagination
    lookup_field = 'uuid'

    @swagger_auto_schema(tags=["Milestone"])
    def post(self, request, *args, **kwargs):
        """ Create main milestone with associated sub milestones """
        required_roles = ["c2c_milestone_admin","c2c_super_admin"]
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

    @swagger_auto_schema(tags=["Milestone"])
    def get(self, request, *args, **kwargs):
        """ list of Milestones """
        required_roles = ["c2c_milestone_admin","c2c_milestone_viewer","c2c_super_admin"]
        result = has_permission(request,required_roles)
        if result["status"] == 200:
            response = self.list(request, *args, **kwargs)
            response.data.update({"result":result})
            return response
        else:
            return Response({"result":result})

class MilestoneDetailAPIView(RetrieveModelMixin, UpdateModelMixin, DestroyModelMixin, GenericAPIView):
    queryset = MainMilestone.objects.all().order_by('-uuid')  # Order by the latest IDs in descending order
    serializer_class = MainMilestoneSerializer
    pagination_class = Pagination
    lookup_field = 'uuid'

    def get_serializer_class(self):
        if self.request.method == 'PATCH':
            return MilestoneUpdateSerializer
        return MainMilestoneSerializer

    @swagger_auto_schema(tags=["Milestone"])
    def get(self, request, *args, **kwargs): #pk
        required_roles = ["c2c_milestone_admin","c2c_milestone_viewer","c2c_viewer","c2c_super_admin"]
        result = has_permission(request,required_roles)
        if result["status"] == 200:
            response = self.retrieve(request, *args, **kwargs)
            response.data.update({"result":result})
            return response
        else:
            return Response({"result":result})

    @swagger_auto_schema(tags=["Milestone"])
    def patch(self, request, *args, **kwargs):
        required_roles = ["c2c_milestone_admin","c2c_super_admin"]
        result = has_permission(request,required_roles)
        if result["status"] == 200:
            username = result['username']
            try:
                instance = self.get_object()
                request_data = request.data.copy()
                request_data['username_updated'] = username
                serializer = self.get_serializer(instance, data=request_data, partial=False)
                serializer.is_valid(raise_exception=True)
                self.perform_update(serializer)
                response_data = serializer.data
                response_data.update({"result": result})
                return Response(response_data, status=status.HTTP_200_OK)
            except Exception as e:
                return Response({"error": str(e), "details": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

    @swagger_auto_schema(tags=["Milestone"])
    def delete(self, request, *args, **kwargs):
        required_roles = ["c2c_milestone_admin","c2c_super_admin"]
        result = has_permission(request,required_roles)
        if result["status"] == 200:
            instance = self.get_object()
            self.perform_destroy(instance)
            return Response({"message": "Milestone deleted successfully","result":result})
        else:
            return Response({"result":result})

class MilestoneDetailCheckView(GenericAPIView):
    def post(self,request,contract_sow_uuid):
        if not contract_sow_uuid:
            return Response({'error': 'contract_sow_uuid is required.'}, status=400)
        exists = MainMilestone.objects.filter(contract_sow_uuid=contract_sow_uuid).exists()
        if exists:
            contract_sow = SowContract.objects.get(uuid=contract_sow_uuid)
            milestone_d = MainMilestone.objects.get(contract_sow_uuid=contract_sow_uuid)
            serializer_data = ContractSowSerializer(contract_sow)
            milestone_data = MainMilestoneSerializer(milestone_d)
            return Response({'exists': exists, "contract_sow_data":serializer_data.data,"milestone_data":milestone_data.data})
        else:
            return Response({'exists': exists,"contract_sow_data":{},"milestone_data":{}})


class CheckMilestoneNameView(GenericAPIView):
    queryset = MainMilestone.objects.all()

    def post(self, request, *args, **kwargs):
        name = request.data.get('name', None)
        if name is None:
            return Response({"error": "Name parameter is required."}, status=status.HTTP_400_BAD_REQUEST)
        name = name.strip()
        exists = MainMilestone.objects.filter(name=name).exists()
        return Response({"exists": exists}, status=status.HTTP_200_OK)
