# app/mistral_client.py
import os
from mistralai import Mistral, DocumentURLChunk

_api_key = os.environ.get("MISTRAL_API_KEY")
if not _api_key:
    raise RuntimeError("MISTRAL_API_KEY env var required")

client = Mistral(api_key=_api_key)
DocumentURLChunk = DocumentURLChunk
