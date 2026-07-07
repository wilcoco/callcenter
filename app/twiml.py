"""Twilio TwiML 응답 생성기."""
from __future__ import annotations

from twilio.twiml.voice_response import Gather, VoiceResponse

from .config import get_settings

GREETING = (
    "안녕하세요, 주식회사 캠스입니다. 문의하실 내용을 말씀해 주시면 확인 후 회신드리겠습니다."
)
GOODBYE = "문의하신 내용은 확인 후 빠르게 회신드리겠습니다. 감사합니다."
NO_INPUT = "죄송합니다, 잘 못 들었어요. 다시 말씀해 주시겠어요?"


def _say_kwargs() -> dict:
    s = get_settings()
    return {"language": s.voice_language, "voice": s.twilio_voice}


def gather_response(prompt: str, action: str) -> str:
    """음성 입력을 받기 위한 <Gather input='speech'> TwiML."""
    s = get_settings()
    resp = VoiceResponse()
    gather = Gather(
        input="speech",
        action=action,
        method="POST",
        language=s.voice_language,
        speech_timeout="auto",
        action_on_empty_result=True,
    )
    gather.say(prompt, **_say_kwargs())
    resp.append(gather)
    # Gather가 비어 결과 없이 끝난 경우를 대비한 재안내
    resp.redirect(action, method="POST")
    return str(resp)


def say_and_hangup(message: str) -> str:
    resp = VoiceResponse()
    resp.say(message, **_say_kwargs())
    resp.hangup()
    return str(resp)


VOICEMAIL_GREETING = (
    "안녕하세요, 주식회사 캠스입니다. 지금은 상담 연결이 어렵습니다. "
    "삐 소리 후 문의 내용과 성함, 회신받으실 연락처를 남겨 주시면 확인 후 회신드리겠습니다."
)


def voicemail_response(max_length: int = 180) -> str:
    """Agent 미접속 시 fallback용 보이스메일 TwiML.

    음성 지정 없이 language만 사용 — ClawOps 호환을 위해 최소 태그로 구성.
    """
    s = get_settings()
    resp = VoiceResponse()
    resp.say(VOICEMAIL_GREETING, language=s.voice_language)
    resp.record(max_length=max_length, play_beep=True, timeout=5)
    resp.say("감사합니다. 확인 후 회신드리겠습니다.", language=s.voice_language)
    resp.hangup()
    return str(resp)
