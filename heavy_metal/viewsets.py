from rest_framework import viewsets, status
from core.permissions import ViewModelPermissions
from rest_framework.response import Response
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from .models import HeavyMetalAnalysis, HeavyMetalParameter, HeavyMetalLimit
from .serializers import (
    HeavyMetalAnalysisListSerializer,
    HeavyMetalAnalysisDetailSerializer,
    HeavyMetalAnalysisCreateSerializer,
    HeavyMetalAnalysisTransitionSerializer,
    HeavyMetalLimitSerializer,
    HeavyMetalParameterSerializer
)
from .permissions import IsAdminOrReadOnly  # Example custom permission

class HeavyMetalLimitViewSet(viewsets.ModelViewSet):
    queryset = HeavyMetalLimit.objects.all()
    serializer_class = HeavyMetalLimitSerializer
    permission_classes = [ViewModelPermissions]

    def get_queryset(self):
        return HeavyMetalLimit.objects.all()

class HeavyMetalParameterViewSet(viewsets.ModelViewSet):
    queryset = HeavyMetalParameter.objects.all()
    serializer_class = HeavyMetalParameterSerializer
    permission_classes = [ViewModelPermissions]

    def get_queryset(self):
        return HeavyMetalParameter.objects.all()

class HeavyMetalAnalysisViewSet(viewsets.ModelViewSet):
    queryset = HeavyMetalAnalysis.objects.all()
    permission_classes = [ViewModelPermissions]

    def get_serializer_class(self):
        if self.action == 'list':
            return HeavyMetalAnalysisListSerializer
        elif self.action == 'retrieve':
            return HeavyMetalAnalysisDetailSerializer
        elif self.action == 'create':
            return HeavyMetalAnalysisCreateSerializer
        return HeavyMetalAnalysisListSerializer

    def get_queryset(self):
        return HeavyMetalAnalysis.objects.all()

    @action(detail=True, methods=['post'], url_path='transition')
    def transition(self, request, pk=None):
        """
        Endpoint to transition the state of a HeavyMetalAnalysis object.
        """
        analysis = self.get_object()  # Fetch the object by primary key (pk)
        serializer = HeavyMetalAnalysisTransitionSerializer(
            data=request.data, context={'request': request, 'analysis': analysis}
        )
        if serializer.is_valid():
            serializer.save()
            return Response(
                {'status': 'State transition successful'}, status=status.HTTP_200_OK
            )
        return Response(
            serializer.errors, status=status.HTTP_400_BAD_REQUEST
        )

    @action(detail=False, methods=['post'], url_path='create-analysis')
    def create_analysis(self, request):
        """
        Custom action to handle creating a new HeavyMetalAnalysis object.
        """
        serializer = HeavyMetalAnalysisCreateSerializer(
            data=request.data, context={'request': request}
        )
        if serializer.is_valid():
            serializer.save()
            return Response(
                serializer.data, status=status.HTTP_201_CREATED
            )
        return Response(
            serializer.errors, status=status.HTTP_400_BAD_REQUEST
        )
