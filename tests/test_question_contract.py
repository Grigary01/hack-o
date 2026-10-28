import pytest
from app.schemas.hotelier import HotelierQuestion
from frontend.question_client import QuestionClient
from frontend.question_stub import StubQuestionAPI


@pytest.mark.parametrize('scenario', ['open', 'pending', 'answered', 'reopened',
                                     'resolved', 'unparsed', 'rejected', 'stale'])
def test_frontend_snapshots_follow_the_typed_question_contract(scenario):
    stub = StubQuestionAPI(scenario=scenario)
    client = QuestionClient(api=stub)
    question = HotelierQuestion.model_validate(client.list_questions()[0])
    assert len(client.list_questions(hotel_id=question.hotel_id, status=question.status)) == 1
    assert client.list_questions(status='answered' if question.status == 'open' else 'open') == []
    assert client.list_questions(hotel_id='another-hotel') == []
    assert client.create_question(**stub.fixture['question_request'])['id'] == question.id
    # UI может менять свою копию JSON, не изменяя исходный снимок заглушки.
    view = client.list_questions()[0]
    view['context']['reasons'].append('local-ui-value')
    assert 'local-ui-value' not in client.list_questions()[0]['context']['reasons']


def test_frontend_stub_can_switch_scenarios_without_a_fake_parser():
    stub = StubQuestionAPI()
    client = QuestionClient(api=stub)
    opened = client.list_questions()[0]
    stub.show('answered')
    assert client.list_questions()[0]['id'] == opened['id']
    assert client.list_questions()[0]['status'] == 'answered'
    stub.show('reopened')
    assert client.list_questions()[0]['context']['reasons'] == ['conflicted']
    with pytest.raises(RuntimeError, match='проверяйте с backend'):
        client.submit_answer(opened['id'], 'Не создавать ложное подтверждение')
