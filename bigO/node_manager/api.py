import datetime

from asgiref.sync import sync_to_async
from ninja import FilterSchema, ModelSchema, Query, Router
from ninja.pagination import paginate
from pydantic import Field

from django.shortcuts import aget_object_or_404

from . import models

router = Router()


class NodeLatestSyncStatOutSchema(ModelSchema):
    class Meta:
        model = models.NodeLatestSyncStat
        fields = ["respond_at"]


class NodeOutSchema(ModelSchema):
    sync_stat: NodeLatestSyncStatOutSchema | None = Field(None, alias="node_nodesyncstat")
    generic_status: models.GenericStatusChoices

    class Meta:
        model = models.Node
        fields = ["id", "name", "downtime_attended"]


class NodePatchInSchema(ModelSchema):
    class Meta:
        model = models.Node
        fields = ["downtime_attended"]
        fields_optional = "__all__"


class NodeFilterSchema(FilterSchema):
    id__in: list[int] | None = None
    is_revoked: bool | None = None
    is_failedover: bool | None = None
    sync_stat__respond_at__lt: datetime.datetime | None = None


@router.get("/nodes", response=list[NodeOutSchema])
@paginate
async def list_nodes(request, filters: NodeFilterSchema = Query(...)):
    nodes = models.Node.objects.select_related("node_nodesyncstat").ann_is_online().ann_generic_status()
    nodes = filters.filter(nodes)
    return await sync_to_async(list)(nodes)


@router.patch("/nodes/{node_id}")
async def patch_node(request, node_id: int, payload: NodePatchInSchema):
    node = await aget_object_or_404(models.Node, id=node_id)
    for attr, value in payload.dict().items():
        setattr(node, attr, value)
    await node.asave()
    return {"success": True}
