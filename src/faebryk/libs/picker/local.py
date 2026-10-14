# This file is part of the faebryk project
# SPDX-License-Identifier: MIT
"""Parts whose CAD assets are supplied by the project, without a catalog lookup."""

from dataclasses import dataclass, field

from faebryk.libs.picker.picker import PickedPart, PickSupplier


class PickSupplierLocal(PickSupplier):
    supplier_id = "local"

    def attach(self, module, part):
        # is_atomic_part supplies the footprint before this part is encountered.
        # A local selection must never fall back to downloading a footprint.
        import faebryk.library._F as F

        if not module.has_trait(F.Footprints.has_associated_footprint):
            raise ValueError("Local part is missing its project footprint")


@dataclass(frozen=True, kw_only=True)
class PickedPartLocal(PickedPart):
    supplier: PickSupplierLocal = field(default_factory=PickSupplierLocal)
