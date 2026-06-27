"""Group ownership graph and effective-interest computation.

Each entity has a ``parent_id`` (empty for the top reporting parent) and an
``ownership_pct`` -- the fraction of the entity held directly by its parent.
Ownership can run through several tiers: a subsidiary's parent may itself be a
subsidiary, so the chain can be more than one link long.

House rule (intentional): the group's EFFECTIVE interest in an entity is the
product of ``ownership_pct`` along the whole chain of parents, from the entity
up to the top parent. Effective interest must be available for EVERY
consolidated subsidiary, because the non-controlling-interest split depends on
it (see ``invprofit``).
"""
from decimal import Decimal


class OwnershipGraph:
    def __init__(self, entities):
        # entities: {entity_id -> row dict}
        self._entities = entities
        self._parent = {}
        self._direct = {}
        for eid, row in entities.items():
            parent = (row.get("parent_id") or "").strip()
            self._parent[eid] = parent
            pct = (row.get("ownership_pct") or "").strip()
            self._direct[eid] = Decimal(pct) if pct else None

    def is_top_parent(self, eid):
        return self._parent.get(eid, "") == ""

    def direct_interest(self, eid):
        """The fraction of ``eid`` held directly by its immediate parent."""
        return self._direct[eid]

    def consolidated_entities(self):
        """Every subsidiary consolidated below the top parent (each entity that
        has a parent). Effective interest is computed for exactly this set."""
        return {eid for eid in self._entities if self._parent[eid]}

    def effective_interest(self, eid):
        """Product of direct ownership up the parent chain to the top parent."""
        pct = Decimal("1")
        cur = eid
        while self._parent.get(cur):
            pct *= self._direct[cur]
            cur = self._parent[cur]
        return pct
