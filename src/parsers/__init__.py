"""Parsers turn one raw source into a SourceBlock (claims + identity hints).
Parsers never normalize-for-merge and never crash the run: a malformed source
yields zero claims, not an exception."""
