#qc/context_processors.py
from __future__ import annotations

import logging

from django.core.exceptions import ObjectDoesNotExist


logger = logging.getLogger(__name__)


def treatment_plant_context(request):


    context = {

        "treatment_plant": None,

        "plant_context": {},

        "plant_has_phases": False,

        "plant_phases": [],

        "plant_water_types": [],

    }


    user = getattr(
        request,
        "user",
        None,
    )


    if not user or not user.is_authenticated:

        return context



    try:

        # =================================================
        # SUPERUSER
        # =================================================

        if user.is_superuser:

            context["plant_context"] = {

                "is_superuser": True,

                "has_phases": False,

                "phases": [],

                "water_types": [],

            }

            return context



        # =================================================
        # ASSIGNED TREATMENT PLANT
        # =================================================

        plant = getattr(
            user,
            "assigned_treatment_plant",
            None,
        )


        if not plant:

            return context



        # =================================================
        # OPTIONAL PHASE SUPPORT
        # =================================================

        phases = []

        try:

            if hasattr(
                plant,
                "phases",
            ):

                phases = list(
                    plant.phases.all()
                )

        except Exception:

            phases = []



        # =================================================
        # AVAILABLE WATER TYPES
        # =================================================

        water_types = []


        try:

            if hasattr(
                plant,
                "sampling_schedules",
            ):

                water_types = list(

                    plant.sampling_schedules

                    .values_list(
                        "water_type",
                        flat=True,
                    )

                    .distinct()

                )

        except Exception:

            water_types = []



        # =================================================
        # FINAL CONTEXT
        # =================================================

        context.update({

            "treatment_plant": plant,


            "plant_has_phases": bool(
                phases
            ),


            "plant_phases": phases,


            "plant_water_types": water_types,


            "plant_context": {

                "id": plant.pk,

                "name": plant.name,

                "has_phases": bool(phases),

                "phases": phases,

                "water_types": water_types,

                "is_superuser": False,

            },

        })


    except ObjectDoesNotExist:

        return context


    except Exception as exc:

        logger.exception(
            "QC treatment plant context failed: %s",
            exc,
        )


    return context