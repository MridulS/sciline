# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2023 Scipp contributors (https://github.com/scipp)
from dataclasses import dataclass
from typing import (
    Any,
    Callable,
    Dict,
    Generic,
    Literal,
    Optional,
    Tuple,
    Type,
    TypeVar,
    Union,
    get_args,
    get_origin,
)

from ._provider import ArgSpec


@dataclass(frozen=True)
class Label:
    tp: type
    index: Any


T = TypeVar('T')


@dataclass(frozen=True)
class Item(Generic[T]):
    label: Tuple[Label, ...]
    tp: Type[T]


Provider = Callable[..., Any]
ProviderKind = Literal['function', 'parameter', 'table']


Key = Union[type, Item[Any]]
Graph = Dict[Key, Tuple[Provider, ArgSpec]]


def get_optional(tp: Key) -> Optional[Any]:
    if get_origin(tp) != Union:
        return None
    args = get_args(tp)
    if len(args) != 2 or type(None) not in args:
        return None
    return args[0] if args[1] == type(None) else args[1]  # noqa: E721


def get_union(tp: Key) -> Optional[Tuple[Any, ...]]:
    if get_origin(tp) != Union:
        return None
    return get_args(tp)
