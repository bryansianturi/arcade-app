"""Sorting algorithms for the visualizer. Each sorts ``values`` in place and yields steps.

Add one by writing a generator and decorating it::

    @sorting_algorithm("Selection")
    def selection_sort(values: list[int]) -> Iterator[SortStep]:
        ...
"""

from __future__ import annotations

from collections.abc import Iterator

from apps.algo_visualizer.logic import Compare, SortStep, Swap, Write, sorting_algorithm


@sorting_algorithm("Bubble")
def bubble_sort(values: list[int]) -> Iterator[SortStep]:
    """Swap neighbours until a pass makes no swaps; each pass parks the largest at the end."""
    end = len(values)
    swapped = True
    while swapped and end > 1:
        swapped = False
        for i in range(end - 1):
            yield Compare(i, i + 1)
            if values[i] > values[i + 1]:
                values[i], values[i + 1] = values[i + 1], values[i]
                swapped = True
                yield Swap(i, i + 1)
        end -= 1


@sorting_algorithm("Insertion")
def insertion_sort(values: list[int]) -> Iterator[SortStep]:
    """Grow a sorted prefix, sliding each new value left into place."""
    for i in range(1, len(values)):
        j = i
        while j > 0:
            yield Compare(j - 1, j)
            if values[j - 1] <= values[j]:
                break
            values[j - 1], values[j] = values[j], values[j - 1]
            yield Swap(j - 1, j)
            j -= 1


@sorting_algorithm("Merge")
def merge_sort(values: list[int]) -> Iterator[SortStep]:
    """Top-down merge sort: sort each half, then merge them back through a buffer."""

    def sort(lo: int, hi: int) -> Iterator[SortStep]:
        if hi - lo < 2:
            return
        mid = (lo + hi) // 2
        yield from sort(lo, mid)
        yield from sort(mid, hi)
        left, right = values[lo:mid], values[mid:hi]
        i = j = 0
        k = lo
        while i < len(left) and j < len(right):
            yield Compare(lo + i, mid + j)
            if left[i] <= right[j]:
                values[k] = left[i]
                i += 1
            else:
                values[k] = right[j]
                j += 1
            yield Write(k)
            k += 1
        for value in left[i:] + right[j:]:
            values[k] = value
            yield Write(k)
            k += 1

    yield from sort(0, len(values))


@sorting_algorithm("Quick")
def quick_sort(values: list[int]) -> Iterator[SortStep]:
    """Quicksort with Lomuto partitioning around a median-of-three pivot."""

    def sort(lo: int, hi: int) -> Iterator[SortStep]:
        while lo < hi:
            mid = (lo + hi) // 2
            # Median of three, moved to the end, avoids the worst case on sorted input.
            for a, b in ((lo, mid), (lo, hi), (mid, hi)):
                yield Compare(a, b)
                if values[a] > values[b]:
                    values[a], values[b] = values[b], values[a]
                    yield Swap(a, b)
            values[mid], values[hi] = values[hi], values[mid]
            yield Swap(mid, hi)
            pivot = values[hi]
            store = lo
            for i in range(lo, hi):
                yield Compare(i, hi)
                if values[i] < pivot:
                    if i != store:
                        values[i], values[store] = values[store], values[i]
                        yield Swap(i, store)
                    store += 1
            if store != hi:
                values[store], values[hi] = values[hi], values[store]
                yield Swap(store, hi)
            # Recurse into the smaller side, loop on the larger: O(log n) stack depth.
            if store - lo < hi - store:
                yield from sort(lo, store - 1)
                lo = store + 1
            else:
                yield from sort(store + 1, hi)
                hi = store - 1

    yield from sort(0, len(values) - 1)
