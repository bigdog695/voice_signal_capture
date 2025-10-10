import logging
import time
from typing import Any, Dict, List, Literal

import httpx
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


@router.post("/ticketGeneration", response_model=TicketResponse)
async def ticket_generation(req: TicketRequest) -> TicketResponse:
    # Trace: request received
    try:
        log_event(
            log,
            'ticket_req_received',
            unique_key=req.unique_key,
            turns=len(req.conversation),
        )
    except Exception:
        pass

    body: Dict[str, List[Dict[str, str]]] = {
        req.unique_key: [{item.source: item.text} for item in req.conversation]
    }

    # Trace: schema transformed for upstream summarizer (log full body)
    try:
        log_event(log, 'ticket_req_transformed', body=body)
    except Exception:
        pass

    try:
        start_ts = time.perf_counter()
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.post(TICKET_INFER_URL, json=body)
            response.raise_for_status()
            payload: Dict[str, Any] = response.json()

        elapsed_ms = int((time.perf_counter() - start_ts) * 1000)

        try:
            log_event(
                log,
                'ticket_upstream_return',
                upstream=TICKET_INFER_URL,
                success=True,
                elapsed_ms=elapsed_ms,
            )
        except Exception:
            pass

        try:
            resp = TicketResponse(**payload)
        except ValidationError as e:
            log_event(log, 'ticket_proxy_invalid_response', upstream=TICKET_INFER_URL, error=str(e))
            raise HTTPException(status_code=502, detail='ticket service invalid response')

        log_event(
            log,
            'ticket_proxy_ok',
            upstream=TICKET_INFER_URL,
            unique_key=req.unique_key,
            type=resp.ticket_type,
            zone=resp.ticket_zone,
            title=resp.ticket_title,
        )
        return resp

    except httpx.TimeoutException as e:
        log_event(log, 'ticket_proxy_timeout', upstream=TICKET_INFER_URL, error=str(e))
        raise HTTPException(status_code=504, detail='ticket service timeout')
    except httpx.HTTPStatusError as e:
        status = e.response.status_code if e.response is not None else 502
        log_event(log, 'ticket_proxy_http_error', upstream=TICKET_INFER_URL, status=status, error=str(e))
        raise HTTPException(status_code=502, detail='ticket service error')
    except HTTPException:
        raise
    except Exception as e:
        # Trace: unexpected failures
        try:
            log_event(log, 'ticket_proxy_error', upstream=TICKET_INFER_URL, error=str(e))
        except Exception:
            pass
        raise HTTPException(status_code=502, detail='ticket proxy failed')
