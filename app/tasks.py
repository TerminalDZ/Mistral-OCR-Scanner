# app/tasks.py
import os
import json
import re
from .mistral_client import client, DocumentURLChunk
from .utils import result_path, update_job_completed, update_job_title

def _extract_markdown_from_ocr(ocr_resp):
    # Try object attributes first
    try:
        pages = None
        if hasattr(ocr_resp, "pages"):
            pages = ocr_resp.pages
        elif isinstance(ocr_resp, dict) and "pages" in ocr_resp:
            pages = ocr_resp["pages"]
        elif hasattr(ocr_resp, "to_dict"):
            d = ocr_resp.to_dict()
            pages = d.get("pages")
        if pages:
            parts = []
            for p in pages:
                if isinstance(p, dict):
                    md = p.get("markdown") or p.get("text")
                else:
                    md = getattr(p, "markdown", None) or getattr(p, "text", None)
                if md:
                    parts.append(str(md))
            if parts:
                return "\n\n".join(parts)
    except Exception:
        pass

    # Fallback: regex from string representation
    try:
        s = str(ocr_resp)
        matches = re.findall(r"markdown=\\?'([^']+)'|markdown=\"([^\"]+)\"", s, re.DOTALL)
        parts = []
        for a, b in matches:
            parts.append(a or b)
        if parts:
            return "\n\n".join(parts)
    except Exception:
        pass

    return None

def _extract_title_from_markdown(markdown_text):
    if not markdown_text:
        return None
    # Take first non-empty line, strip hashes and length-limit
    for line in markdown_text.splitlines():
        line = line.strip()
        if not line:
            continue
        # remove leading markdown heading markers
        cleaned = re.sub(r'^#+\s*', '', line)
        cleaned = cleaned.strip()
        if cleaned:
            return cleaned[:120]
    # fallback to first 120 chars
    s = markdown_text.strip()
    return s[:120] if s else None

def process_document(file_path: str = None, document_url: str = None, job_id: str = None, do_annotations: bool = False, annotation_schema: dict = None, do_qna: bool = False):
    result = {"job_id": job_id, "steps": []}
    signed_url = None
    pages_processed = None
    title_generated = None

    try:
        # upload local file to Mistral Files to get signed URL
        if file_path:
            up = client.files.upload(file={"file_name": os.path.basename(file_path), "content": open(file_path, "rb")}, purpose="ocr")
            signed_obj = client.files.get_signed_url(file_id=up.id)
            signed_url = signed_obj.url
        elif document_url:
            signed_url = document_url

        # store document_url
        result["document_url"] = signed_url

        # OCR
        ocr_resp = client.ocr.process(model="mistral-ocr-latest", document=DocumentURLChunk(document_url=signed_url), include_image_base64=False)
        result["ocr"] = ocr_resp
        result["steps"].append("ocr_done")

        # pages info
        try:
            if hasattr(ocr_resp, "usage_info") and getattr(ocr_resp.usage_info, "pages_processed", None):
                pages_processed = ocr_resp.usage_info.pages_processed
        except Exception:
            pages_processed = None

        # Try to extract markdown
        full_markdown = _extract_markdown_from_ocr(ocr_resp)
        if full_markdown:
            result["full_markdown"] = full_markdown

        # Derive title: first prefer model-generated title, otherwise from markdown
        # Generate title using mistral-small-latest (best-effort)
        try:
            model = os.environ.get("DOC_QNA_MODEL", "mistral-small-latest")
            messages = [
                {"role":"user", "content":[{"type":"text", "text":"Create a short descriptive title (max 8 words) for the following document. Return only the title as plain text."}, {"type":"document_url","document_url": signed_url}]}
            ]
            chat_resp = client.chat.complete(model=model, messages=messages)
            try:
                title_generated = chat_resp.choices[0].message.content
            except Exception:
                title_generated = str(chat_resp)
            if isinstance(title_generated, (list, dict)):
                title_generated = str(title_generated)
            if title_generated:
                title_generated = title_generated.strip().strip('"').strip("'")
                # keep short
                title_generated = title_generated[:120]
                result["title"] = title_generated
        except Exception:
            title_generated = None

        # If no title from model, try extract from markdown
        if not title_generated and full_markdown:
            t = _extract_title_from_markdown(full_markdown)
            if t:
                title_generated = t
                result["title"] = title_generated

        # optional annotations
        if do_annotations and annotation_schema:
            ann = client.ocr.process(model="mistral-ocr-latest", document=DocumentURLChunk(document_url=signed_url), bbox_annotation_format={"type":"json_schema", "json_schema": annotation_schema}, include_image_base64=False)
            result["annotations"] = ann
            result["steps"].append("annotations_done")

        # optional QnA immediate summary
        if do_qna:
            try:
                model2 = os.environ.get("DOC_QNA_MODEL", "mistral-small-latest")
                messages = [
                    {"role":"user", "content":[{"type":"text","text":"Provide a short summary of the document."}, {"type":"document_url","document_url":signed_url}]}
                ]
                chat_resp2 = client.chat.complete(model=model2, messages=messages)
                result["qna_summary"] = chat_resp2.choices[0].message.content
                result["steps"].append("qna_done")
            except Exception:
                pass

        # Save result JSON
        rpath = result_path(job_id)
        with open(rpath, "w", encoding="utf-8") as f:
            try:
                json.dump(result, f, default=str, ensure_ascii=False, indent=2)
            except TypeError:
                f.write(str(result))

        # update DB with title (if extracted or generated)
        update_job_completed(job_id, rpath, status="completed", pages=pages_processed, title=title_generated)
        # also ensure title field updated if not set by update_job_completed above
        if title_generated:
            try:
                update_job_title(job_id, title_generated)
            except Exception:
                pass

        return {"status":"completed", "job_id": job_id}
    except Exception as e:
        err_obj = {"status":"failed", "error": str(e)}
        with open(result_path(job_id), "w", encoding="utf-8") as f:
            json.dump(err_obj, f, ensure_ascii=False, indent=2)
        update_job_completed(job_id, result_path(job_id), status="failed", pages=pages_processed, title=title_generated)
        raise
