import re
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.commerce_models import Order, ReturnRequest
from app.customer_assistant.models import CustomerSupportCase, CustomerSupportConversation, CustomerSupportMessage
from app.customer_assistant.service import CustomerAssistantService
from app.models import User
from app.security.gateway import DLP


@dataclass(frozen=True)
class ConversationReply:
    conversation_id: int
    answer: str
    intent: str
    evidence: dict


class ConversationService:
    def __init__(self, session: Session):
        self._session = session

    def create_conversation(self, user_id: int) -> CustomerSupportConversation:
        conversation = CustomerSupportConversation(user_id=user_id)
        self._session.add(conversation)
        self._session.commit()
        self._session.refresh(conversation)
        return conversation

    def reply(self, conversation_id: int, user_id: int, message: str) -> ConversationReply:
        conversation = self._conversation(conversation_id, user_id)
        masked, _ = DLP.mask(message)
        intent = _intent(masked)
        self._session.add(CustomerSupportMessage(
            conversation_id=conversation.id,
            sender="CUSTOMER",
            content_masked=masked,
            intent=intent,
            evidence={},
        ))
        customer = self._session.get(User, user_id)
        history = [
            {"sender": row.sender, "content_masked": row.content_masked}
            for row in self._session.query(CustomerSupportMessage)
            .filter_by(conversation_id=conversation.id)
            .order_by(CustomerSupportMessage.id.desc())
            .limit(9)
            .all()[::-1]
        ]
        if intent == "ORDER_STATUS":
            order_no = _order_no(masked)
            query = self._session.query(Order).filter_by(user_id=user_id)
            order = query.filter_by(order_no=order_no).first() if order_no else query.order_by(Order.id.desc()).first()
            answer = f"最近订单状态：{order.status.value}" if order else "未找到你的订单。"
            evidence = {"order_id": order.id} if order else {}
        elif intent in {"ACTION_REQUEST", "AFTER_SALES_POLICY"}:
            answer, evidence = "该请求需要人工或售后流程处理，可点击转人工继续。", {}
        else:
            result = CustomerAssistantService(self._session).reply(customer, masked, {}, history=history)
            answer = result.answer
            evidence = {"products": [
                {"product_id": source.product_id, "source_url": source.source_url}
                for source in result.sources
            ]}
        self._session.add(CustomerSupportMessage(
            conversation_id=conversation.id,
            sender="ASSISTANT",
            content_masked=answer,
            intent=intent,
            evidence=evidence,
        ))
        self._session.commit()
        return ConversationReply(conversation.id, answer, intent, evidence)

    def escalate(self, conversation_id: int, user_id: int, reason: str = "USER_REQUEST") -> CustomerSupportCase:
        self._conversation(conversation_id, user_id)
        case = self._session.query(CustomerSupportCase).filter_by(conversation_id=conversation_id).one_or_none()
        if case:
            return case
        latest = self._session.query(CustomerSupportMessage).filter_by(conversation_id=conversation_id).order_by(CustomerSupportMessage.id.desc()).first()
        case = CustomerSupportCase(conversation_id=conversation_id, user_id=user_id, trigger_reason=reason, summary_masked=latest.content_masked if latest else None)
        self._session.add(case)
        self._session.commit()
        return case

    def _conversation(self, conversation_id: int, user_id: int) -> CustomerSupportConversation:
        conversation = self._session.query(CustomerSupportConversation).filter_by(
            id=conversation_id, user_id=user_id
        ).one_or_none()
        if conversation is None:
            raise LookupError("会话不存在")
        return conversation


def _intent(message: str) -> str:
    if re.search(r"退款|退货|取消订单|修改订单", message): return "ACTION_REQUEST"
    if re.search(r"订单|物流|发货", message): return "ORDER_STATUS"
    if re.search(r"售后|保修|换货", message): return "AFTER_SALES_POLICY"
    return "CATALOG"


def _order_no(message: str) -> str | None:
    match = re.search(r"(?:订单号|订单)\s*([A-Za-z0-9-]{6,64})", message)
    return match.group(1) if match else None
