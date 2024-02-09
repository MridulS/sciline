# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2023 Scipp contributors (https://github.com/scipp)
from __future__ import annotations

import inspect
from html import escape
from typing import Any, Generator, Optional, Sequence, Tuple, TypeVar, Union

from ._provider import Provider
from ._utils import keyname
from .scheduler import DaskScheduler, NaiveScheduler, Scheduler
from .typing import Graph, Item, Key

T = TypeVar("T")


def _list_items(items: Sequence[str]) -> str:
    return '\n'.join(
        (
            '<ul>',
            ('\n'.join((f'<li>{escape(it)}</li>' for it in items))),
            '</ul>',
        )
    )


def _list_max_n_then_hide(items: Sequence[str], n: int = 5, header: str = '') -> str:
    def wrap(s: str) -> str:
        return '\n'.join(
            (
                '<div class="task-graph-detail-list">'
                '<style> .task-graph-detail-list ul { margin-top: 0; } </style>',
                s,
                '</div>',
            )
        )

    return wrap(
        '\n'.join(
            (
                header,
                _list_items(items),
            )
        )
        if len(items) <= n
        else '\n'.join(
            (
                '<details>',
                '<style>',
                'details[open] .task-graph-summary ul { display: none; }',
                '</style>',
                '<summary class="task-graph-summary">',
                header,
                _list_items((*items[:n], '...')),
                '</summary>',
                _list_items(items),
                '</details>',
            )
        )
    )


class TaskGraph:
    """
    Holds a concrete task graph and keys to compute.

    Task graphs are typically created by :py:class:`sciline.Pipeline.build`. They allow
    for computing all or a subset of the results in the graph.
    """

    def __init__(
        self,
        *,
        graph: Graph,
        keys: Union[type, Tuple[type, ...], Item[T], Tuple[Item[T], ...]],
        scheduler: Optional[Scheduler] = None,
    ) -> None:
        self._graph = graph
        self._keys = keys
        if scheduler is None:
            try:
                scheduler = DaskScheduler()
            except ImportError:
                scheduler = NaiveScheduler()
        self._scheduler = scheduler

    def compute(
        self,
        keys: Optional[
            Union[type, Tuple[type, ...], Item[T], Tuple[Item[T], ...]]
        ] = None,
    ) -> Any:
        """
        Compute the result of the graph.

        Parameters
        ----------
        keys:
            Optional list of keys to compute. This can be used to override the keys
            stored in the graph instance. Note that the keys must be present in the
            graph as intermediate results, otherwise KeyError is raised.

        Returns
        -------
        If ``keys`` is a single type, returns the single result that was computed.
        If ``keys`` is a tuple of types, returns a dictionary with type as keys
        and the corresponding results as values.

        """
        if keys is None:
            keys = self._keys
        if isinstance(keys, tuple):
            results = self._scheduler.get(self._graph, list(keys))
            return dict(zip(keys, results))
        else:
            return self._scheduler.get(self._graph, [keys])[0]

    def nodes(self) -> Generator[Union[Key, Provider], None, None]:
        """Iterate over all nodes of the graph.

        Nodes are both keys, i.e., the types of values that can be computed
        and providers.

        Returns
        -------
        :
            Iterable over keys and providers.
        """
        for key, provider in self._graph.items():
            yield key
            yield provider

    def edges(
        self,
    ) -> Generator[Union[tuple[Key, Provider], tuple[Provider, Key]], None, None]:
        """Iterate over all edges of the graph.

        Returns
        -------
        :
            Iterable over pairs ``(source, target)`` which indicate a directed edge
            from ``source`` to ``target``.
            There are two cases:

            - ``source`` is a key, ``target`` is a provider.
            - ``source`` is a provider, ``target`` is a key.
        """
        for key, provider in self._graph.items():
            yield provider, key
            for arg in provider.arg_spec.keys():
                yield arg, provider

    def visualize(
        self, **kwargs: Any
    ) -> graphviz.Digraph:  # type: ignore[name-defined] # noqa: F821
        """
        Return a graphviz Digraph object representing the graph.

        Parameters
        ----------
        kwargs:
            Keyword arguments passed to :py:class:`graphviz.Digraph`.
        """
        from .visualize import to_graphviz

        return to_graphviz(self._graph, **kwargs)

    def serialize(self) -> dict[str, Any]:
        node_ids = _UniqueNodeId()
        nodes = []
        edges = []
        for key, provider in self._graph.items():
            key_id = node_ids.get(key)
            nodes.append(_serialize_data_node(key, key_id))
            _ = provider

        return {
            'directed': True,
            'multigraph': False,
            'nodes': nodes,
            'edges': edges,
        }

    def _repr_html_(self) -> str:
        leafs = sorted(
            [
                escape(keyname(key))
                for key in (
                    self._keys if isinstance(self._keys, tuple) else [self._keys]
                )
            ]
        )
        roots = sorted(
            {
                escape(keyname(key))
                for key, provider in self._graph.items()
                if provider.kind != 'function'
            }
        )
        scheduler = escape(str(self._scheduler))

        def head(word: str) -> str:
            return f'<h5>{word}</h5>'

        return '\n'.join(
            (
                '<style>.task-graph-repr h5 { display: inline; }</style>',
                '<div class="task-graph-repr">',
                head('Output keys: '),
                ','.join(leafs),
                '<br>',
                head('Scheduler: '),
                scheduler,
                '<br>',
                _list_max_n_then_hide(roots, header=head('Input keys:')),
                '</div>',
            )
        )


def _serialize_data_node(key: Key, key_id: str) -> dict[str, str]:
    return {'id': key_id, 'kind': 'data', 'label': str(key), 'type': _key_qualname(key)}


def _key_qualname(key: Key) -> str:
    module = inspect.getmodule(key)
    if module is None:
        return str(key)
    return f'{module.__name__}.{str(key)}'


class _UniqueNodeId:
    def __init__(self) -> None:
        self._assigned: dict[int, str] = {}
        self._next = 0

    def get(self, obj: Any) -> str:
        try:
            return self._assigned[id(obj)]
        except KeyError:
            self._assigned[id(obj)] = str(self._next)
            self._next += 1
            return self._assigned[id(obj)]
