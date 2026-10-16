from rest_flex_fields import FlexFieldsModelSerializer
from rest_framework.serializers import ReadOnlyField

from . import models


class EmployeeCardSerializer(FlexFieldsModelSerializer):
    """
    ## Expansions

    To activate relation expansion add the desired fields as a comma separated
    list to the `expand` query parameter like this:

        ?expand=<field>,<field>,<field>,...

    The following relational fields can be expanded:

     * `person`

    """

    full_name = ReadOnlyField()
    organization_name = ReadOnlyField()
    has_apple_pass = ReadOnlyField()
    has_google_pass = ReadOnlyField()

    expandable_fields = {
        "person": (
            "outpost.django.campusonline.serializers.AuthenticatedPersonSerializer",
            {"many": False},
        ),
    }

    class Meta:
        model = models.EmployeeCard
        fields = (
            "id",
            "person",
            "full_name",
            "organization_name",
            "has_apple_pass",
            "has_google_pass",
            "created_at",
            "updated_at",
        )
