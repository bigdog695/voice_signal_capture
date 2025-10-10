import asyncio
import importlib.util
import logging
from pathlib import Path
from typing import Any, Callable, Dict, List, Literal, Optional, Tuple, Union

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ValidationError

from common.logging_utils import log_event


# Default upstream URL; actual value will be taken from the test helper if available.
TICKET_INFER_URL = "http://100.120.241.10:8001/summarize"


log = logging.getLogger("WSServer")
router = APIRouter()


class ConversationItem(BaseModel):
    source: Literal["citizen", "hot-line"]
    text: str


class TicketRequest(BaseModel):
    unique_key: str
    conversation: List[ConversationItem]


class TicketResponse(BaseModel):
    ticket_type: str
    ticket_zone: str
    ticket_title: str
    ticket_content: str


_SEND_TEST_REQUEST: Optional[
    Callable[..., Union[bool, Tuple[bool, Optional[Dict[str, Any]]]]]
] = None
_UPSTREAM_URL: str = TICKET_INFER_URL


def _load_send_test_request() -> Callable[..., Union[bool, Tuple[bool, Optional[Dict[str, Any]]]]]:
    global _SEND_TEST_REQUEST, _UPSTREAM_URL
    if _SEND_TEST_REQUEST is None:
        module_path = Path(__file__).resolve().parent.parent / "ai-generated-ticket" / "test_service.py"
        spec = importlib.util.spec_from_file_location("ticket_test_service", module_path)
        if not spec or not spec.loader:
            raise RuntimeError("Unable to load test_service.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        send_func = getattr(module, "send_test_request", None)
        if send_func is None:
            raise RuntimeError("send_test_request not found in test_service.py")
        _SEND_TEST_REQUEST = send_func
        _UPSTREAM_URL = getattr(module, "SUMMARIZE_URL", TICKET_INFER_URL)
    return _SEND_TEST_REQUEST


@router.post("/ticketGeneration", response_model=TicketResponse)
async def ticket_generation(req: TicketRequest) -> TicketResponse:
    body: Dict[str, List[Dict[str, str]]] = {
        req.unique_key: [{item.source: item.text} for item in req.conversation]
    }

    try:
        send_test_request = _load_send_test_request()
        result = await asyncio.to_thread(
            send_test_request,
            "ticketGeneration",
            body,
            return_response=True,
        )

        if isinstance(result, tuple):
            success, payload = result
        else:
            success, payload = bool(result), None

        if not success or not payload:
            log_event(
                log,
                'ticket_proxy_error',
                upstream=_UPSTREAM_URL,
                unique_key=req.unique_key,
                error='send_test_request failed',
            )
            raise HTTPException(status_code=502, detail='ticket service error')

        try:
            resp = TicketResponse(**payload)
        except ValidationError as e:
            log_event(log, 'ticket_proxy_invalid_response', upstream=_UPSTREAM_URL, error=str(e))
            raise HTTPException(status_code=502, detail='ticket service invalid response')

        log_event(
            log,
            'ticket_proxy_ok',
            upstream=_UPSTREAM_URL,
            unique_key=req.unique_key,
            type=resp.ticket_type,
            zone=resp.ticket_zone,
            title=resp.ticket_title,
        )
        return resp

    except HTTPException:
        raise
    except Exception as e:
        log_event(log, 'ticket_proxy_error', upstream=_UPSTREAM_URL, error=str(e))
        raise HTTPException(status_code=502, detail='ticket proxy failed')

