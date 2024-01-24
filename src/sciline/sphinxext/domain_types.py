# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2024 Scipp contributors (https://github.com/scipp)
"""A Sphinx extension for improved typehints rendering.

`sphinx-autodoc-typehints <https://github.com/tox-dev/sphinx-autodoc-typehints>`_
implements formatting for typehints but often results in hard-to-read annotations
for :class:`typing.NewType`.
As those are ubiquitous when using Sciline, this extension improves formatting.

Usage
-----

This extension relies on
`sphinx-autodoc-typehints <https://github.com/tox-dev/sphinx-autodoc-typehints>`_
for the core implementation of typehints rendering.
Install it as well as Sciline and add both to ``extensions`` in your conf.py:

.. code-block:: python

    extensions = [
        ...,
        'sphinx-autodoc-typehints',
        'sciline.sphinxext.domain_types'
    ]

``sciline.sphinxext.domain_types`` registers a custom ``typehints_formatter``
used by ``sphinx-autodoc-typehints``, so do not define your own!

Options
~~~~~~~

- ``sciline_domain_types_prefix`` (default ``''``): Strip this prefix from type names.
  For example, if a type is defined as ``mypackage.types.SomeType``, setting
  ``sciline_domain_types_prefix = 'mypackage'`` results in this type being rendered
  as ``types.SomeType``.
- ``sciline_domain_types_extra_aliases`` (default ``{}``):
  ``sciline.sphinxext.domain_types`` can render aliases instead of the regular
  type names. This is useful, e.g., for abbreviating long types or types defined
  in internal modules. ``sciline.sphinxext.domain_types`` defines some default
  aliases for Scipp, e.g., ``{'scipp._scipp.core.DataArray': 'scipp.DataArray', ...}``
  which means that occurrences of ``scipp._scipp.core.DataArray`` are rendered as
  ``scipp.DataArray``. Aliases defined in ``sciline_domain_types_extra_aliases``
  are added to the defaults but don't override them.
"""

from sphinx.application import Sphinx
from sphinx.config import Config
from typing import Optional, Any, NewType


def setup(app: Sphinx)->dict[str,Any]:
    """Setup sciline.sphinxext.domain_types."""
    app.add_config_value('sciline_domain_types_prefix',
                         default='',
                         rebuild='env', types=str)
    app.add_config_value('sciline_domain_types_extra_aliases',
                         default={},
                         rebuild='env', types=dict[str,str])
    app.config.typehints_formatter = _typehints_formatter
    return {'version': 1, 'parallel_read_safe': True, 'parallel_write_safe': True}


_DEFAULT_ALIASES = {
    'scipp._scipp.core.DataArray': 'scipp.DataArray',
    'scipp._scipp.core.Dataset': 'scipp.Dataset',
    'scipp._scipp.core.DType': 'scipp.DType',
    'scipp._scipp.core.Unit': 'scipp.Unit',
    'scipp._scipp.core.Variable': 'scipp.Variable',
    'scipp.core.data_group.DataGroup': 'scipp.DataGroup',
}


def _typehints_formatter(annotation, config: Config) -> Optional[str]:
    """Format typehints with improved NewType handling."""
    prefix = config.sciline_domain_types_prefix
    aliases = _DEFAULT_ALIASES | config.sciline_domain_types_extra_aliases

    if _is_new_type(annotation):
        return _format_new_type(annotation, prefix, aliases)
    if _is_type_alias_type(annotation):
        return _format_type_alias_type(annotation, prefix, aliases)
    return None


def _is_new_type(annotation: Any) -> bool:
    # TODO Switch to isinstance(key, NewType) once our minimum is Python 3.10
    # Note that we cannot pass mypy in Python<3.10 since NewType is not a type.
    return hasattr(annotation, '__supertype__')


def _format_new_type(annotation: NewType, prefix: str,aliases:dict[str,str]) -> str:
    return (
        f'{_internal_link(annotation, "class", prefix)}'
        f' ({_link(annotation.__supertype__, "class",aliases)})'
    )


def _is_type_alias_type(annotation: Any) -> bool:
    try:
        from typing import TypeAliasType

        return isinstance(annotation, TypeAliasType)
    except ImportError:
        return False  # pre python 3.12


def _format_type_alias_type(annotation: Any, prefix: str,aliases:dict[str,str]) -> str:
    alias = _internal_link(annotation, "class", prefix, annotation.__type_params__)
    value = _link(annotation.__value__, "class", aliases, _get_type_args(annotation.__value__))
    return f'{alias} ({value})'


def _get_type_args(ty: type) -> tuple[type, ...]:
    if (args := getattr(ty, '__args__', None)) is not None:
        return args  # e.g. list[int]
    return ty.__type_params__


def _internal_link(
    annotation: Any,
    kind: str,
    prefix: str,
    type_params: Optional[tuple[type, ...]] = None,
) -> str:
    target = f'{annotation.__module__}.{annotation.__name__}'
    label = f'{annotation.__module__.removeprefix(prefix+".")}.{annotation.__name__}'
    if type_params:
        label += f'[{", ".join(ty.__name__ for ty in type_params)}]'
    return f':{kind}:`{label} <{target}>`'


def _link(ty: type, kind: str,aliases:dict[str,str], type_params: Optional[tuple[type, ...]] = None) -> str:
    if ty.__module__ == 'builtins':
        target = ty.__name__
    else:
        target = f'{ty.__module__}.{ty.__name__}'
    label = aliases.get(target, target)
    if type_params:
        label += f'[{", ".join(ty.__name__ for ty in type_params)}]'
    return f':{kind}:`{label} <{target}>`'
