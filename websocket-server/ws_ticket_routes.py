import logging
from typing import List, Literal

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from common.logging_utils import log_event


# Configure the upstream ticket inference URL here
TICKET_INFER_URL = "http://127.0.0.1:9000/ticketGeneration"


log = logging.getLogger("WSServer")
router = APIRouter()


class ConversationItem(BaseModel):
    source: Literal["citizen", "hot-line"] = Field(..., description="消息来源：市民(citizen)或热线(hot-line)")
    text: str = Field(..., description="消息内容（可为中文）")


class TicketRequest(BaseModel):
    unique_key: str = Field(..., description="会话唯一标识")
    conversations: List[ConversationItem] = Field(..., min_items=1, description="对话数组，至少一条")


class TicketResponse(BaseModel):
    ticket_type: str
    ticket_zone: str
    ticket_title: str
    ticket_content: str


@router.post("/ticketGeneration", response_model=TicketResponse)
async def ticket_generation(req: TicketRequest) -> TicketResponse:
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.post(TICKET_INFER_URL, json=req.dict())
            r.raise_for_status()
            data = r.json()
        resp = TicketResponse(**data)
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
    except httpx.HTTPError as e:
        status = getattr(e.response, 'status_code', 502) if getattr(e, 'response', None) else 502
        log_event(log, 'ticket_proxy_http_error', upstream=TICKET_INFER_URL, status=status, error=str(e))
        raise HTTPException(status_code=502, detail='ticket service error')
    except Exception as e:
        log_event(log, 'ticket_proxy_error', upstream=TICKET_INFER_URL, error=str(e))
        raise HTTPException(status_code=502, detail='ticket proxy failed')
