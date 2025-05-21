from collections.abc import Awaitable, Callable
from typing import Generic, Literal, TypeAlias, TypeVar

import pydantic
from asgiref.sync import sync_to_async

from django.core.paginator import Paginator
from django.db.models import QuerySet

OutputRecordT = TypeVar("OutputRecordT", bound=pydantic.BaseModel)
InputRecordT = TypeVar("InputRecordT", bound=QuerySet)


class Pagination(pydantic.BaseModel):
    num_pages: int
    num_records: int
    num_per_page: int
    current_page_num: int


class Search(pydantic.BaseModel):
    query: str | None


class Sorting(pydantic.BaseModel):
    is_asc: bool | None


class Column(pydantic.BaseModel):
    sorting: Sorting | None


class ListPage(pydantic.BaseModel, Generic[OutputRecordT]):
    prefix: str | None
    pagination: Pagination | None
    search: Search | None
    records: list[OutputRecordT]
    columns: dict[str, Column]


class User(pydantic.BaseModel):
    id: str
    title: str
    last_sublink_at_repr: str | None
    last_usage_at_repr: str | None
    online_status: Literal["online", "offline", "never"]
    used_bytes: int
    total_limit_bytes: int
    expires_in_seconds: int


UsersColumns = Literal["a", "b"]


search_callback_type: TypeAlias = Callable[[QuerySet[InputRecordT], str], Awaitable[QuerySet[InputRecordT]]] | None
render_record_callback_type: TypeAlias = Callable[[InputRecordT], Awaitable[OutputRecordT]]
sort_callback_type: TypeAlias = Callable[
    [QuerySet[InputRecordT], list[tuple[str, bool]]], Awaitable[QuerySet[InputRecordT], list[tuple[str, bool]]]
]


class ListPageHandler(Generic[InputRecordT, OutputRecordT]):
    def __init__(
        self,
        request,
        queryset: QuerySet[InputRecordT] | list[InputRecordT],
        search_callback: search_callback_type,
        render_record_callback: render_record_callback_type,
        sort_callback: sort_callback_type | None = None,
        sortables: set[str] = None,
        prefix: str | None = None,
        default_per_page=25,
    ):
        assert (sortables and sort_callback) or not (sortables or sort_callback)
        self.sortables = sortables
        self.sort_callback = sort_callback

        self.request = request
        self.queryset = queryset
        self.defualt_per_page = default_per_page
        self.prefix = prefix or ""
        self.render_record_callback = render_record_callback
        self.search_callback = search_callback

    @property
    def search_q(self) -> str | None:
        return self.request.GET.get(f"{self.prefix}_search")

    async def searched_queryset(self):
        if self.search_callback is None or self.search_q is None:
            return self.queryset
        if not hasattr(self, "_searched_queryset"):
            setattr(self, "_searched_queryset", await self.search_callback(self.queryset, self.search_q))
        return self._searched_queryset

    @property
    def sort_q(self) -> str | None:
        return self.request.GET.get(f"{self.prefix}_sort")

    @property
    def sorted_els(self) -> tuple[str, bool]:
        return self._sorted_els

    async def sorted_queryset(self):
        searched_queryset = await self.searched_queryset()
        if self.sort_callback is None or self.sort_q is None:
            self._sorted_els = []
            return searched_queryset
        if not hasattr(self, "_sorted_queryset"):
            sort_els = [
                (i.removeprefix("-").removeprefix(f"{self.prefix}_"), not i.startswith("-"))
                for i in self.sort_q.split(",")
            ]
            qs, sorted_els = await self.sort_callback(searched_queryset, sort_els)
            setattr(self, "_sorted_queryset", qs)
            setattr(self, "_sorted_els", sorted_els)
        return self._sorted_queryset

    @property
    def per_page(self) -> int:
        return self.request.GET.get(f"{self.prefix}_per_page", self.defualt_per_page)

    async def paginator(self):
        if not hasattr(self, "_paginator"):
            setattr(self, "_paginator", Paginator(await self.sorted_queryset(), self.per_page))
        return self._paginator

    async def page(self):
        if not hasattr(self, "_page"):
            page_number = self.request.GET.get(f"{self.prefix}_page_number", self.request.GET.get("page", 1))
            paginator = await self.paginator()
            setattr(self, "_page", await sync_to_async(paginator.get_page)(page_number))
        return self._page

    async def to_response(self):
        page = await self.page()
        search = Search(query=self.search_q) if self.search_callback else None
        if not self.sortables:
            columns = None
        else:
            columns = {}
            for i in self.sortables:
                r = [j for j in self.sorted_els if j[0] == i]
                is_asc = r[0][1] if r else None
                columns[i] = Column(sorting=Sorting(is_asc=is_asc))
        return ListPage[OutputRecordT](
            prefix=self.prefix,
            pagination=Pagination(
                num_pages=page.paginator.num_pages,
                current_page_num=page.number,
                num_per_page=page.paginator.per_page,
                num_records=page.paginator.count,
            ),
            search=search,
            records=[await self.render_record_callback(i) for i in await sync_to_async(list)(page)],
            columns=columns,
        )
