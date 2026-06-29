"""Twilio TwiML 응답 생성기."""
from __future__ import annotations

from twilio.twiml.voice_response import Gather, VoiceResponse

from .config import get_settings

GREETING = "안녕하세요, 무엇을 도와드릴까요? 용건을 말씀해 주세요."
GOODBYE = "문의 주셔서 감사합니다. 담당 팀에서 신속히 연락드리겠습니다. 좋은 하루 되세요."
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
