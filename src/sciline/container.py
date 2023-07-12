# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2023 Scipp contributors (https://github.com/scipp)
from __future__ import annotations

from functools import wraps
from typing import (
    Any,
    Callable,
    Dict,
    List,
    Type,
    TypeVar,
    get_args,
    get_origin,
    get_type_hints,
)

from dask.delayed import Delayed, delayed


def _delayed(func: Callable[..., Any]) -> Callable[..., Delayed]:
    """
    Decorator to make a function return a delayed object.

    In contrast to dask.delayed, this uses functools.wraps, to preserve the
    type hints, which is a prerequisite for injecting args based on their type hints.
    """

    @wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Delayed:
        task: Delayed = delayed(func)(*args, **kwargs)
        return task

    return wrapper


T = TypeVar('T')


class UnsatisfiedRequirement(Exception):
    pass


def _is_compatible_type_tuple(
    requested: tuple[type, ...], provided: tuple[type | TypeVar, ...]
) -> bool:
    for req, prov in zip(requested, provided):
        if isinstance(prov, TypeVar):
            continue
        if req != prov:
            return False
    return True


class Container:
    def __init__(self, funcs: List[Callable[..., Any]], /):
        """
        Create a :py:class:`Container` from a list of functions.

        Parameters
        ----------
        funcs:
            List of functions to be injected. Must be annotated with type hints.
        """
        self._providers: Dict[type, Callable[..., Any]] = {}
        self._cache: Dict[type, Delayed] = {}
        for func in funcs:
            self.insert(func)

    def insert(self, provider: Callable[..., Any]) -> None:
        key = get_type_hints(provider)['return']
        parametrized = get_origin(key) is not None
        # if (origin := get_origin(key)) is not None:

        #    key = origin if any(isinstance(arg, TypeVar) for arg in args) else key
        if (not parametrized) and (key in self._providers):
            raise ValueError(f'Provider for {key} already exists')
        if parametrized:
            subproviders = self._providers.setdefault(get_origin(key), {})
            args = get_args(key)
            if args in subproviders:
                raise ValueError(f'Provider for {key} already exists')
            subproviders[args] = _delayed(provider)
        else:
            self._providers[key] = _delayed(provider)

    def _call(self, func: Callable[..., Delayed], bound: Dict[TypeVar, Any]) -> Delayed:
        tps = get_type_hints(func)
        del tps['return']
        args: Dict[str, Any] = {}
        for name, tp in tps.items():
            if isinstance(tp, TypeVar):
                tp = bound[tp]
            elif (origin := get_origin(tp)) is not None:
                tp = origin[
                    tuple(
                        bound[arg] if isinstance(arg, TypeVar) else arg
                        for arg in get_args(tp)
                    )
                ]
            args[name] = self._get(tp)
        return func(**args)

    def _get(self, tp: Type[T], /) -> Delayed:
        # When building a workflow, there are two common problems:
        #
        # 1. Intermediate results are used more than once.
        # 2. Intermediate results are large, so we generally do not want to keep them
        #    in memory longer than necessary.
        #
        # To address these problems, we can internally build a graph of tasks, instead
        # of directly creating dependencies between functions. Currently we use Dask
        # for this. We cache call results to ensure Dask will recognize the task
        # as the same object) and also wrap the function in dask.delayed.
        if (cached := self._cache.get(tp)) is not None:
            return cached
        if tp in self._providers:
            key = tp
            direct = True
        elif (origin := get_origin(tp)) in self._providers:
            key = origin
            direct = False
        else:
            raise UnsatisfiedRequirement("No provider found for type", tp)

        provider = self._providers[key]
        bound: Dict[TypeVar, Any] = {}
        if not direct:
            requested = get_args(tp)
            matches = []
            for args, subprovider in provider.items():
                if _is_compatible_type_tuple(requested, args):
                    matches.append((args, subprovider))
            if len(matches) == 0:
                raise UnsatisfiedRequirement("No provider found for type", tp)
            elif len(matches) > 1:
                raise KeyError(
                    "Multiple providers found for type", tp, "with arguments", requested
                )
            args, subprovider = matches[0]
            provider = subprovider
            bound = dict(zip(args, requested))

        result = self._call(provider, bound)
        self._cache[tp] = result
        return result

    def get(self, tp: Type[T], /) -> Delayed:
        # We are slightly abusing Python's type system here, by using the
        # self._get to get T, but actually it returns a Delayed that can
        # compute T. We'd like to use Delayed[T], but that is not supported yet:
        # https://github.com/dask/dask/pull/9256
        return self._get(tp)

    def compute(self, tp: Type[T], /) -> T:
        task = self.get(tp)
        result: T = task.compute()  # type: ignore
        return result
