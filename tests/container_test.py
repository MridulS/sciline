# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2023 Scipp contributors (https://github.com/scipp)
from dataclasses import dataclass
from typing import Generic, NewType, TypeVar, get_origin

import dask
import pytest

import sciline as sl

# We use dask with a single thread, to ensure that call counting below is correct.
dask.config.set(scheduler='synchronous')


def int_to_float(x: int) -> float:
    return 0.5 * x


def make_int() -> int:
    return 3


def int_float_to_str(x: int, y: float) -> str:
    return f"{x};{y}"


def test_make_container_sets_up_working_container():
    container = sl.Container([int_to_float, make_int])
    assert container.compute(float) == 1.5
    assert container.compute(int) == 3


def test_make_container_does_not_autobind():
    container = sl.Container([int_to_float])
    with pytest.raises(sl.UnsatisfiedRequirement):
        container.compute(float)


def test_intermediate_computed_once():
    ncall = 0

    def provide_int() -> int:
        nonlocal ncall
        ncall += 1
        return 3

    container = sl.Container([int_to_float, provide_int, int_float_to_str])
    assert container.compute(str) == "3;1.5"
    assert ncall == 1


def test_get_returns_task_that_computes_result():
    container = sl.Container([int_to_float, make_int])
    task = container.get(float)
    assert hasattr(task, 'compute')
    assert task.compute() == 1.5


def test_multiple_get_calls_can_be_computed_without_repeated_calls():
    ncall = 0

    def provide_int() -> int:
        nonlocal ncall
        ncall += 1
        return 3

    container = sl.Container([int_to_float, provide_int, int_float_to_str])
    task1 = container.get(float)
    task2 = container.get(str)
    assert dask.compute(task1, task2) == (1.5, '3;1.5')
    assert ncall == 1


def test_make_container_with_subgraph_template():
    ncall = 0

    def provide_int() -> int:
        nonlocal ncall
        ncall += 1
        return 3

    Param = TypeVar('Param')

    class Float(sl.Scope[Param], float):
        ...

    class Str(sl.Scope[Param], str):
        ...

    def int_float_to_str(x: int, y: Float[Param]) -> Str[Param]:
        return Str(f"{x};{y}")

    Run1 = NewType('Run1', int)
    Run2 = NewType('Run2', int)
    Result = NewType('Result', str)

    def float1() -> Float[Run1]:
        return Float[Run1](1.5)

    def float2() -> Float[Run2]:
        return Float[Run2](2.5)

    def use_strings(s1: Str[Run1], s2: Str[Run2]) -> Result:
        return Result(f"{s1};{s2}")

    container = sl.Container(
        [provide_int, float1, float2, use_strings, int_float_to_str],
    )
    assert container.get(Result).compute() == "3;1.5;3;2.5"
    assert ncall == 1


Param = TypeVar('Param')


class Str(sl.Scope[Param], str):
    ...


def f(x: Param) -> Str[Param]:
    return Str(f'{x}')


def test_container_from_templated():
    def make_float() -> float:
        return 1.5

    def combine(x: Str[int], y: Str[float]) -> str:
        return f"{x};{y}"

    container = sl.Container([make_int, make_float, combine, f])
    assert container.compute(Str[int]) == '3'
    assert container.compute(Str[float]) == '1.5'
    assert container.compute(str) == '3;1.5'


T1 = TypeVar('T1')
T2 = TypeVar('T2')


class SingleArg(Generic[T1]):
    ...


class MultiArg(Generic[T1, T2]):
    ...


def test_understanding_of_Generic():
    assert get_origin(MultiArg) is None
    with pytest.raises(TypeError):
        MultiArg[int]  # to few parameters
    assert get_origin(MultiArg[int, T2]) is MultiArg
    assert get_origin(MultiArg[T1, T2]) is MultiArg


def test_understanding_of_TypeVar():
    assert T1 != T2
    assert T1 == T1
    assert T1 is T1
    assert TypeVar('T3') != TypeVar('T3')


def test_TypeVars_params_are_not_associated_unless_they_match():
    T1 = TypeVar('T1')
    T2 = TypeVar('T2')

    class A(Generic[T1]):
        ...

    class B(Generic[T2]):
        ...

    def source() -> A[int]:
        return A[int]()

    def not_matching(x: A[T1]) -> B[T2]:
        return B[T2]()

    def matching(x: A[T1]) -> B[T1]:
        return B[T1]()

    container = sl.Container([source, not_matching])
    with pytest.raises(KeyError):
        container.compute(B[int])

    container = sl.Container([source, matching])
    container.compute(B[int])


def test_multi_Generic_with_fully_bound_arguments():
    T1 = TypeVar('T1')
    T2 = TypeVar('T2')

    @dataclass
    class A(Generic[T1, T2]):
        first: T1
        second: T2

    def source() -> A[int, float]:
        return A[int, float](1, 2.0)

    container = sl.Container([source])
    assert container.compute(A[int, float]) == A[int, float](1, 2.0)


def test_multi_Generic_with_partially_bound_arguments():
    T1 = TypeVar('T1')
    T2 = TypeVar('T2')

    @dataclass
    class A(Generic[T1, T2]):
        first: T1
        second: T2

    def source() -> float:
        return 2.0

    def partially_bound(x: T1) -> A[int, T1]:
        return A[int, T1](1, x)

    container = sl.Container([source, partially_bound])
    assert container.compute(A[int, float]) == A[int, float](1, 2.0)


def test_multi_Generic_with_multiple_unbound():
    T1 = TypeVar('T1')
    T2 = TypeVar('T2')

    @dataclass
    class A(Generic[T1, T2]):
        first: T1
        second: T2

    def int_source() -> int:
        return 1

    def float_source() -> float:
        return 2.0

    def unbound(x: T1, y: T2) -> A[T1, T2]:
        return A[T1, T2](x, y)

    container = sl.Container([int_source, float_source, unbound])
    assert container.compute(A[int, float]) == A[int, float](1, 2.0)
    assert container.compute(A[float, int]) == A[float, int](2.0, 1)


def test_distinct_fully_bound_instances_yield_distinct_results():
    T1 = TypeVar('T1')

    @dataclass
    class A(Generic[T1]):
        value: T1

    def int_source() -> A[int]:
        return A[int](1)

    def float_source() -> A[float]:
        return A[float](2.0)

    container = sl.Container([int_source, float_source])
    assert container.compute(A[int]) == A[int](1)
    assert container.compute(A[float]) == A[float](2.0)


def test_distinct_partially_bound_instances_yield_distinct_results():
    T1 = TypeVar('T1')

    @dataclass
    class A(Generic[T1, T2]):
        first: T1
        second: T2

    def str_source() -> str:
        return 'a'

    def int_source(x: T1) -> A[int, T1]:
        return A[int, T1](1, x)

    def float_source(x: T1) -> A[float, T1]:
        return A[float, T1](2.0, x)

    container = sl.Container([str_source, int_source, float_source])
    assert container.compute(A[int, str]) == A[int, str](1, 'a')
    assert container.compute(A[float, str]) == A[float, str](2.0, 'a')


def test_multiple_matching_partial_providers_raises():
    T1 = TypeVar('T1')

    @dataclass
    class A(Generic[T1, T2]):
        first: T1
        second: T2

    def int_source() -> int:
        return 1

    def float_source() -> float:
        return 2.0

    def provider1(x: T1) -> A[int, T1]:
        return A[int, T1](1, x)

    def provider2(x: T2) -> A[T2, float]:
        return A[T2, float](x, 2.0)

    container = sl.Container([int_source, float_source, provider1, provider2])
    assert container.compute(A[int, int]) == A[int, int](1, 1)
    assert container.compute(A[float, float]) == A[float, float](2.0, 2.0)
    with pytest.raises(KeyError):
        container.compute(A[int, float])
