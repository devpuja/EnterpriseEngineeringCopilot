from contextlib import contextmanager
from contextvars import ContextVar
from typing import Iterator


_context: ContextVar[dict[str, str]] = ContextVar("observability_context", default={})


def current_context() -> dict[str, str]:
    return dict(_context.get())


@contextmanager
def bind_context(**fields: str) -> Iterator[None]:
    token = _context.set({**_context.get(), **fields})
    try:
        yield
    finally:
        _context.reset(token)
