"""Shipping email/document parsing for the P2 preview: no database writes, no mailbox access."""
from .fields import PARSER_VERSION, extract_fields
from .pipeline import parse_shipping_document, parse_shipping_email

__all__ = ['PARSER_VERSION', 'extract_fields', 'parse_shipping_document', 'parse_shipping_email']
