"""Normalizers: turn raw extracted values into canonical formats.

Each function is pure (input -> output, no side effects) and returns None when it
cannot confidently normalize, so callers can decide to drop the value rather than
invent one. 'Unknown becomes null, never invented.'
"""
