from __future__ import annotations

from customer_ai_runtime.domain.models import HandoffPackage, MessageRole, Session, SessionState

from customer_ai_runtime.application.runtime import zh


class HandoffService:
    def create_package(self, session: Session, reason: str) -> HandoffPackage:
        history = session.messages[-10:]
        user_messages = [message.content for message in history if message.role == MessageRole.USER]
        intent = user_messages[-1] if user_messages else zh("\\u7528\\u6237\\u9700\\u8981\\u4eba\\u5de5")
        summary = " | ".join(message.content for message in history[-6:])
        recommended_reply = zh(
            "\\u4eba\\u5de5\\u5ba2\\u670d\\u53ef\\u5148\\u786e\\u8ba4\\u7528\\u6237\\u8bc9\\u6c42"
            "\\uff0c\\u518d\\u57fa\\u4e8e\\u5f53\\u524d\\u6458\\u8981\\u7ee7\\u7eed\\u5904\\u7406\\u3002"
        )
        session.state = SessionState.WAITING_HUMAN
        session.waiting_human = True
        return HandoffPackage(
            tenant_id=session.tenant_id,
            session_id=session.session_id,
            reason=reason,
            summary=summary,
            intent=intent,
            recommended_reply=recommended_reply,
            history=history,
        )

