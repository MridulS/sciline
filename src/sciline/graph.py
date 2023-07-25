# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2023 Scipp contributors (https://github.com/scipp)
from typing import Any, Callable, Dict, List, Tuple, get_args, get_origin

from graphviz import Digraph

from .pipeline import Graph


def to_graphviz(graph: Graph) -> Digraph:
    """
    Convert output of :py:class:`sciline.Pipeline.get_graph` to a graphviz graph.

    Parameters
    ----------
    graph:
        Output of :py:class:`sciline.Pipeline.get_graph`.
    """
    dot = Digraph(strict=True)
    for p, (p_name, args, ret) in _format_graph(graph).items():
        dot.node(p, p_name, shape='ellipse')
        for arg in args:
            dot.node(arg, arg, shape='rectangle')
            dot.edge(arg, p)
        dot.node(ret, ret, shape='rectangle')
        dot.edge(p, ret)
    return dot


def _format_graph(graph: Graph) -> Dict[str, Tuple[str, List[str], str]]:
    return {
        _format_provider(provider, ret): (
            provider.__qualname__,
            [_format_type(a) for a in args.values()],
            _format_type(ret),
        )
        for ret, (provider, args) in graph.items()
    }


def _format_provider(provider: Callable[..., Any], ret: type) -> str:
    return f'{provider.__qualname__}_{_format_type(ret)}'


def _format_type(tp: type) -> str:
    """
    Helper for _format_graph.

    If tp is a generic such as Array[float], we want to return 'Array[float]',
    but strip all module prefixes from the type name as well as the params.
    We may make this configurable in the future.
    """
    base = tp.__name__ if hasattr(tp, '__name__') else str(tp).split('.')[-1]
    if get_origin(tp) is not None:
        params = [_format_type(param) for param in get_args(tp)]
        return f'{base}[{", ".join(params)}]'
    else:
        return base