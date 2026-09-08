from app.models import Role, Ticket, User


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
    product = Product(brand="vivo", name="X100", status=ProductStatus.ACTIVE)
    db_session.add(product)
    db_session.flush()
    db_session.add(CustomerCatalogChunk(
        product_id=product.id, source_url="https://example.test/x100", source_hash="source",
        content="vivo X100 适合拍照", content_hash="content", embedding=[0.0] * 512,
    ))
    db_session.commit()

    service = ConversationService(db_session)
    conversation = service.create_conversation(customer.id)
    service.reply(conversation.id, customer.id, "推荐拍照手机，我的电话是13812340000")

    messages = db_session.query(CustomerSupportMessage).filter_by(conversation_id=conversation.id).all()
    assert [message.sender for message in messages] == ["CUSTOMER", "ASSISTANT"]
    assert "13812340000" not in messages[0].content_masked
    assert "138****0000" in messages[0].content_masked
