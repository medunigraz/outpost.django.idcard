from outpost.django.base.decorators import docstring_format
from rest_flex_fields.views import FlexFieldsMixin
from rest_framework.permissions import IsAuthenticated
from rest_framework.viewsets import ReadOnlyModelViewSet

from . import (
    models,
    serializers,
)


@docstring_format(
    model=models.EmployeeCard.__doc__,
    serializer=serializers.EmployeeCardSerializer.__doc__,
)
class EmployeeCardViewSet(FlexFieldsMixin, ReadOnlyModelViewSet):
    """
    List digital employee ID cards.

    Everyone sees their own card. Holders of the `idcard.view_employeecard`
    permission see all of them.

    {model}
    {serializer}
    """

    queryset = models.EmployeeCard.objects.select_related("person")
    serializer_class = serializers.EmployeeCardSerializer
    permission_classes = (IsAuthenticated,)
    permit_list_expands = ("person",)

    def get_queryset(self):
        qs = super().get_queryset()
        if self.request.user.has_perm("idcard.view_employeecard"):
            return qs
        return qs.filter(person__username=self.request.user.username)
