"""Tests for gateway-level "report in pdf" shortcut handling."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from gateway.config import Platform
from gateway.platforms.base import MessageEvent, MessageType
from gateway.session import SessionSource


def _make_source() -> SessionSource:
    return SessionSource(
        platform=Platform.TELEGRAM,
        chat_id="100",
        chat_type="dm",
        user_id="200",
        user_name="tester",
    )


def _make_event(text: str, message_type: MessageType = MessageType.TEXT) -> MessageEvent:
    return MessageEvent(text=text, message_type=message_type, source=_make_source())


def _make_runner():
    from gateway.run import GatewayRunner

    runner = object.__new__(GatewayRunner)
    runner._running_agents = {}
    runner._pending_messages = {}
    runner._pending_approvals = {}
    runner.hooks = MagicMock()
    runner.hooks.emit = AsyncMock()
    runner._is_user_authorized = MagicMock(return_value=True)
    runner.session_store = MagicMock()
    return runner


class TestReportPdfShortcutHelpers:
    def test_matcher_detects_pdf_report_request(self):
        from gateway.run import GatewayRunner

        assert GatewayRunner._wants_report_pdf_request("send me the report in pdf") is True
        assert GatewayRunner._wants_report_pdf_request("pdf summary please") is True
        assert GatewayRunner._wants_report_pdf_request("send report") is False
        assert GatewayRunner._wants_report_pdf_request("show pdf file") is False

    @pytest.mark.asyncio
    async def test_shortcut_returns_media_tag_when_pdf_available(self):
        from gateway.run import GatewayRunner

        runner = _make_runner()
        runner._fetch_report_pdf_bytes = AsyncMock(return_value=b"%PDF-1.4 fake")
        runner._fetch_report_text = AsyncMock(return_value=None)
        event = _make_event("send me the report in pdf")

        with patch("gateway.run.cache_document_from_bytes", return_value="/tmp/report.pdf"):
            result = await GatewayRunner._handle_report_pdf_shortcut(runner, event)

        assert result is not None
        assert "MEDIA:/tmp/report.pdf" in result
        runner._fetch_report_text.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_shortcut_falls_back_to_text_report(self):
        from gateway.run import GatewayRunner

        runner = _make_runner()
        runner._fetch_report_pdf_bytes = AsyncMock(return_value=None)
        runner._fetch_report_text = AsyncMock(return_value="Mission summary text")
        event = _make_event("send me the report in pdf")

        result = await GatewayRunner._handle_report_pdf_shortcut(runner, event)

        assert result is not None
        assert "text report" in result.lower()
        assert "Mission summary text" in result

    @pytest.mark.asyncio
    async def test_shortcut_ignores_non_matching_message(self):
        from gateway.run import GatewayRunner

        runner = _make_runner()
        runner._fetch_report_pdf_bytes = AsyncMock(return_value=b"%PDF")
        runner._fetch_report_text = AsyncMock(return_value="unused")
        event = _make_event("hello rover")

        result = await GatewayRunner._handle_report_pdf_shortcut(runner, event)

        assert result is None
        runner._fetch_report_pdf_bytes.assert_not_awaited()
        runner._fetch_report_text.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_shortcut_text_helper_handles_transcribed_voice_text(self):
        from gateway.run import GatewayRunner

        runner = _make_runner()
        runner._fetch_report_pdf_bytes = AsyncMock(return_value=b"%PDF-1.4 fake")
        runner._fetch_report_text = AsyncMock(return_value=None)

        with patch("gateway.run.cache_document_from_bytes", return_value="/tmp/report.pdf"):
            result = await GatewayRunner._handle_report_pdf_shortcut_text(
                runner,
                '[The user sent a voice message~ Here\'s what they said: "send me the report in pdf"]',
            )

        assert result is not None
        assert "MEDIA:/tmp/report.pdf" in result


class TestHandleMessageIntegration:
    @pytest.mark.asyncio
    async def test_handle_message_returns_shortcut_before_session_creation(self):
        from gateway.run import GatewayRunner

        runner = _make_runner()
        runner._handle_report_pdf_shortcut = AsyncMock(return_value="MEDIA:/tmp/report.pdf")
        runner.session_store.get_or_create_session.side_effect = AssertionError("should not create session")
        event = _make_event("send me the report in pdf")

        result = await GatewayRunner._handle_message(runner, event)

        assert result == "MEDIA:/tmp/report.pdf"
        runner._handle_report_pdf_shortcut.assert_awaited_once_with(event)
