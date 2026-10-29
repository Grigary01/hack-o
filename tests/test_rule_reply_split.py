"""Разбор ответа отельера правилами: значение одной части не приписывается чужим номерам."""
import pytest

from app.hotelier.rule_reply_parser import parse_hotelier_reply


@pytest.mark.parametrize('text,claims,unparsed', [
    # Баг: «нет» про 101 записывалось как «нет вида» в 201–203.
    ('В номерах 201-203 есть вид на море, в 101 нет.', {'201': True, '202': True, '203': True}, ['в 101 нет']),
    ('В номерах 201-203 есть вид на море, а 101 без вида', {'201': True, '202': True, '203': True}, ['а 101 без вида']),
    ('В номерах 201, 202, 203 есть вид на море.', {'201': True, '202': True, '203': True}, []),
    ('В номере 501 есть вид на море. В номере 101 нет вида на море.', {'501': True, '101': False}, []),
    ('В номере 305 на 3-м этаже есть вид на море', {'305': True}, []),
])
def test_values_stay_with_their_own_rooms(text, claims, unparsed):
    result = parse_hotelier_reply('sea_view', text)
    assert {c.room_number: c.value for c in result.claims} == claims
    assert result.unparsed == unparsed
