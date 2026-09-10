import pytest
from types import SimpleNamespace

from app.models import Role, Ticket, User


def _seed_open_case(db_session):
    from app.customer_assistant.models import CustomerSupportCase, CustomerSupportConversation

    customer = User(username="support-message-customer", password_hash="unused", role=Role.CUSTOMER)
    other_customer = User(username="support-message-other", password_hash="unused", role=Role.CUSTOMER)
    agent = User(username="support-message-agent", password_hash="unused", role=Role.CS)
    db_session.add_all([customer, other_customer, agent])
    db_session.flush()
    conversation = CustomerSupportConversation(user_id=customer.id)
    db_session.add(conversation)
    db_session.flush()
    case = CustomerSupportCase(
        conversation_id=conversation.id,
        user_id=customer.id,
        trigger_reason="USER_REQUEST",
    )
    db_session.add(case)
    db_session.commit()
    return conversation, case, customer, other_customer, agent


def test_agent_reply_is_masked_requires_assignment_and_messages_are_ordered(db_session):
    from app.customer_assistant.conversations import ConversationService
    from app.customer_assistant.models import CustomerSupportMessage

    conversation, case, customer, other_customer, agent = _seed_open_case(db_session)
    db_session.add_all([
        CustomerSupportMessage(conversation_id=conversation.id, sender="CUSTOMER", content_masked="第一条", evidence={}),
        CustomerSupportMessage(conversation_id=conversation.id, sender="ASSISTANT", content_masked="第二条", evidence={}),
    ])
    db_session.commit()
    service = ConversationService(db_session)

    with pytest.raises(LookupError):
        service.list_messages(conversation.id, other_customer.id, Role.CUSTOMER)
    with pytest.raises(ValueError):
        service.add_agent_message(case.id, agent.id, "请联系 13812340000")

    case.status = "IN_PROGRESS"
    case.assigned_to = agent.id
    db_session.commit()

    message = service.add_agent_message(case.id, agent.id, "请联系 13812340000")
    assert message.sender == "AGENT"
    assert "13812340000" not in message.content_masked
    assert "138****0000" in message.content_masked
    assert [row.content_masked for row in service.list_messages(conversation.id, customer.id, Role.CUSTOMER)] == [
        "第一条", "第二条", "请联系 138****0000",
    ]


def test_agent_reply_locks_assigned_in_progress_case_before_writing():
    from app.customer_assistant.conversations import ConversationService

    class LockedCaseQuery:
        def __init__(self):
            self.filters = None
            self.locked = False

        def filter_by(self, **kwargs):
            self.filters = kwargs
            return self

        def with_for_update(self):
            self.locked = True
            return self

        def one_or_none(self):
            return SimpleNamespace(conversation_id=9, status="IN_PROGRESS", assigned_to=7)

    class Session:
        def __init__(self):
            self.query_result = LockedCaseQuery()

        def query(self, _model):
            return self.query_result

        def add(self, _message):
            pass

        def commit(self):
            pass

        def refresh(self, _message):
            pass

    session = Session()
    ConversationService(session).add_agent_message(5, 7, "已领取")

    assert session.query_result.filters == {"id": 5, "status": "IN_PROGRESS", "assigned_to": 7}
    assert session.query_result.locked is True


def test_customer_support_case_is_distinct_from_refund_ticket(db_session):
    from app.customer_assistant.models import CustomerSupportCase, CustomerSupportConversation

    customer = User(username="support-conversation-customer", password_hash="unused", role=Role.CUSTOMER)
    db_session.add(customer)
    db_session.flush()
    conversation = CustomerSupportConversation(user_id=customer.id)
    db_session.add(conversation)
    db_session.commit()

    case = CustomerSupportCase(
        conversation_id=conversation.id,
        user_id=customer.id,
        trigger_reason="USER_REQUEST",
    )
    db_session.add(case)
    db_session.commit()

    assert case.conversation_id == conversation.id
    assert db_session.query(Ticket).count() == 0


def test_conversation_persists_masked_customer_and_assistant_turns(db_session):
    from app.commerce_models import Product, ProductStatus
    from app.customer_assistant.conversations import ConversationService
    from app.customer_assistant.models import CustomerCatalogChunk, CustomerSupportMessage

    customer = User(username="support-turn-customer", password_hash="unused", role=Role.CUSTOMER)
    db_session.add(customer)
    db_session.flush()
    product = Product(
        brand="vivo", name="X100", description="旗舰影像手机", image_url="https://example.test/x100.jpg",
        category="PHONE", status=ProductStatus.ACTIVE,
    )
    db_session.add(product)
    db_session.flush()
    db_session.add(CustomerCatalogChunk(
        product_id=product.id, source_url="https://example.test/x100", source_hash="source",
        content="vivo X100 适合拍照", content_hash="content", embedding=[0.0] * 512,
    ))
    db_session.commit()

    service = ConversationService(db_session)
    conversation = service.create_conversation(customer.id)
    reply = service.reply(conversation.id, customer.id, "推荐拍照手机，我的电话是13812340000")

    messages = db_session.query(CustomerSupportMessage).filter_by(conversation_id=conversation.id).all()
    assert [message.sender for message in messages] == ["CUSTOMER", "ASSISTANT"]
    assert "13812340000" not in messages[0].content_masked
    assert "138****0000" in messages[0].content_masked
    assert reply.evidence == {
        "products": [{
            "product_id": product.id, "product_name": "X100", "description": "旗舰影像手机",
            "image_url": "https://example.test/x100.jpg", "category": "PHONE", "source_url": "https://example.test/x100",
        }]
    }
    assert messages[1].evidence == reply.evidence


def test_conversation_products_evidence_preserves_catalog_relevance_order(db_session):
    from app.commerce_models import Product, ProductStatus
    from app.customer_assistant.conversations import ConversationService
    from app.customer_assistant.models import CustomerCatalogChunk

    customer = User(username="support-evidence-order-customer", password_hash="unused", role=Role.CUSTOMER)
    db_session.add(customer)
    db_session.flush()
    lower_match = Product(brand="vivo", name="X100", category="PHONE", status=ProductStatus.ACTIVE)
    higher_match = Product(brand="vivo", name="Y200", category="PHONE", status=ProductStatus.ACTIVE)
    db_session.add_all([lower_match, higher_match])
    db_session.flush()
    db_session.add_all([
        CustomerCatalogChunk(
            product_id=lower_match.id, source_url="https://example.test/x100", source_hash="x100-source",
            content="vivo X100 适合拍照", content_hash="x100-content", embedding=[0.0] * 512,
        ),
        CustomerCatalogChunk(
            product_id=higher_match.id, source_url="https://example.test/y200", source_hash="y200-source",
            content="vivo Y200 手机拍照", content_hash="y200-content", embedding=[0.0] * 512,
        ),
    ])
    db_session.commit()

    service = ConversationService(db_session)
    conversation = service.create_conversation(customer.id)
    reply = service.reply(conversation.id, customer.id, "推荐拍照手机")

    assert reply.evidence["products"] == [
        {"product_id": higher_match.id, "product_name": "Y200", "description": None, "image_url": None, "category": "PHONE", "source_url": "https://example.test/y200"},
        {"product_id": lower_match.id, "product_name": "X100", "description": None, "image_url": None, "category": "PHONE", "source_url": "https://example.test/x100"},
    ]
