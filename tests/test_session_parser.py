import json
from pathlib import Path


def _jsonl(tmp_path, messages):
    f = tmp_path / "session.jsonl"
    f.write_text("\n".join(json.dumps(m) for m in messages))
    return f


def _user_msg(text, uuid="u1"):
    return {"type": "user", "uuid": uuid,
            "timestamp": "2026-01-01T10:00:00.000Z",
            "message": {"role": "user", "content": text}}


def _asst_msg(text, uuid="a1"):
    return {"type": "assistant", "uuid": uuid,
            "timestamp": "2026-01-01T10:01:00.000Z",
            "message": {"role": "assistant", "content": text}}


def test_parses_user_and_assistant(tmp_path):
    from hub.data.session_parser import SessionParser, MessageType
    f = _jsonl(tmp_path, [_user_msg("hello"), _asst_msg("hi")])
    result = SessionParser().parse(f)
    assert len(result) == 2
    assert result[0].type == MessageType.USER
    assert result[0].text == "hello"
    assert result[1].type == MessageType.ASSISTANT


def test_filters_queue_operation(tmp_path):
    from hub.data.session_parser import SessionParser
    f = _jsonl(tmp_path, [{"type": "queue-operation"}, _user_msg("ok")])
    result = SessionParser().parse(f)
    assert len(result) == 1


def test_hides_progress_by_default(tmp_path):
    from hub.data.session_parser import SessionParser
    f = _jsonl(tmp_path, [
        {"type": "progress", "uuid": "p1", "timestamp": "2026-01-01T10:00:00.000Z",
         "message": {"role": "assistant", "content": "[tool]"}},
        _user_msg("hello"),
    ])
    assert len(SessionParser().parse(f)) == 1
    assert len(SessionParser(include_progress=True).parse(f)) == 2


def test_content_as_list(tmp_path):
    from hub.data.session_parser import SessionParser
    msg = {"type": "assistant", "uuid": "a1",
           "timestamp": "2026-01-01T10:00:00.000Z",
           "message": {"role": "assistant", "content": [
               {"type": "text", "text": "part one"},
               {"type": "text", "text": " part two"},
           ]}}
    result = SessionParser().parse(_jsonl(tmp_path, [msg]))
    assert "part one" in result[0].text
    assert "part two" in result[0].text


def test_skips_malformed_lines(tmp_path):
    from hub.data.session_parser import SessionParser
    f = tmp_path / "s.jsonl"
    f.write_text('{"type":"user"}\nNOT JSON\n' +
                 json.dumps(_user_msg("good")))
    result = SessionParser().parse(f)
    assert len(result) == 1
    assert result[0].text == "good"


def test_content_includes_tool_use(tmp_path):
    from hub.data.session_parser import SessionParser
    msg = {"type": "assistant", "uuid": "a1",
           "timestamp": "2026-01-01T10:00:00.000Z",
           "message": {"role": "assistant", "content": [
               {"type": "text", "text": "Let me read that file."},
               {"type": "tool_use", "id": "toolu_123", "name": "Read",
                "input": {"file_path": "/tmp/foo.py"}},
           ]}}
    result = SessionParser().parse(_jsonl(tmp_path, [msg]))
    assert "Read" in result[0].text
    assert "/tmp/foo.py" in result[0].text


def test_content_includes_tool_result(tmp_path):
    from hub.data.session_parser import SessionParser
    msg = {"type": "assistant", "uuid": "a1",
           "timestamp": "2026-01-01T10:00:00.000Z",
           "message": {"role": "assistant", "content": [
               {"type": "tool_result", "tool_use_id": "toolu_123",
                "content": "file contents here"},
           ]}}
    result = SessionParser().parse(_jsonl(tmp_path, [msg]))
    assert "file contents here" in result[0].text


def test_content_includes_thinking(tmp_path):
    from hub.data.session_parser import SessionParser
    msg = {"type": "assistant", "uuid": "a1",
           "timestamp": "2026-01-01T10:00:00.000Z",
           "message": {"role": "assistant", "content": [
               {"type": "thinking", "thinking": "I need to consider the edge cases..."},
               {"type": "text", "text": "Here is my answer."},
           ]}}
    result = SessionParser(include_progress=True).parse(_jsonl(tmp_path, [msg]))
    assert "I need to consider" in result[0].text
    assert "Here is my answer" in result[0].text
