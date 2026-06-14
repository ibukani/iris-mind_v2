"""Typed error taxonomy for the gRPC ingress boundary.

The gRPC ingress layer is expected to surface a small, well-defined set of
exception categories so that ``map_exception_to_grpc`` can translate each
into a stable gRPC status code without resorting to a broad ``except
Exception`` fallback.

Concrete catches at the servicer entry point should use the narrowest
exception type that still describes the failure rather than catching
``Exception`` or ``BaseException``. The classes in this module are part
of that contract:

- :class:`GrpcMappingError` describes a DTO conversion failure. It is a
  :class:`ValueError` subclass because the failure usually means the
  request did not satisfy the proto schema.
- :class:`IngressError` is the umbrella marker for the rest of the
  expected error space. ``LLMProviderError`` does not inherit from it
  today, but new ingress-specific failure types can subclass it so a
  single ``except IngressError`` clause can be used as the last
  auditable fallback.

A catch-all ``except Exception`` is intentionally NOT used at the
ingress boundary. Anything outside the categories listed in
:mod:`iris.adapters.grpc.server` is allowed to propagate, which makes
unexpected failures visible during development and prevents the broad
handler from silently masking programming errors.
"""

from __future__ import annotations


class IngressError(Exception):
    """Base class for errors expected at the gRPC ingress boundary.

    Concrete catches should use this base or a more specific subclass
    (e.g. :class:`iris.adapters.llm.diagnostics.LLMProviderError`) rather
    than ``Exception`` so the fallback path is narrow and auditable.
    """


__all__ = ["IngressError"]
