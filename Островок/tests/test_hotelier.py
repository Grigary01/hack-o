import pytest
from app.hotelier.dialogue import parse_hotelier_reply, ask_hotelier, submit_answer, confirm_answer
from app.features.service import resolve_feature


def test_free_text_room_range_and_negation():
    result=parse_hotelier_reply('sea_view','В номерах 301–305 вид на море, все на 3-м этаже.')
    assert len(result.claims)==5 and not result.unparsed
    assert all(c.floor==3 and c.value is True for c in result.claims)
    result=parse_hotelier_reply('sea_view','В номере 302 нет вида на море.')
    assert result.claims[0].value is False


@pytest.mark.parametrize('text',[
    'В номерах 301–305 вид на море, кроме 302.',
    'Возможно, в номере 301 вид на море.',
    'В номере 301 вид на море только летом.',
    'Во всех номерах вид на море.',
    'В номере 301 не гарантирован вид на море.',
    'В номерах 100–99999 вид на море.',
])
def test_ambiguous_reply_requires_review(text):
    result=parse_hotelier_reply('sea_view',text)
    assert result.unparsed


def test_confirmation_is_explicit_persistent_and_idempotent(repo):
    h=repo.hotels()[0]
    q=ask_hotelier(repo,h.id,'sea_view')
    assert ask_hotelier(repo,h.id,'sea_view')['id']==q['id']
    answer=submit_answer(repo,q['id'],'В номерах 301–305 вид на море, все на 3-м этаже.')
    assert not repo.observations(h.id,'sea_view')
    result=confirm_answer(repo,answer['id'],True)
    assert len(result['observation_ids'])==5
    assert confirm_answer(repo,answer['id'],True)['idempotent']
    assert len(repo.observations(h.id,'sea_view'))==5
    obs=repo.observations(h.id,'sea_view')[0]
    assert obs.evidence.source.type=='hotelier_simulated'
    assert obs.evidence.raw_excerpt==answer['text']
    assert resolve_feature([obs],obs.subject_id,'sea_view').value is None


def test_rejected_or_partial_answer_never_creates_observation(repo):
    h=repo.hotels()[0]
    q=ask_hotelier(repo,h.id,'sea_view')
    partial=submit_answer(repo,q['id'],'В номере 301 вид на море. Кроме зимы.')
    with pytest.raises(ValueError):confirm_answer(repo,partial['id'],True)
    confirm_answer(repo,partial['id'],False)
    with pytest.raises(ValueError):confirm_answer(repo,partial['id'],True)
    assert not repo.observations(h.id,'sea_view')
