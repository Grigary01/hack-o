from app.ml.query_parser import FixtureQueryParser, ParserError
from scripts.evaluate_parser import measure, dimension


def test_metrics_expose_operator_error_and_keep_failed_calls_in_denominator():
    text = 'До пляжа не более 0.5 км пешком'
    expected = FixtureQueryParser().parse(text)
    gold = [{'text': text, 'expected': expected.model_dump(mode='json')}] * 2

    class PartlyBrokenParser:
        calls = 0

        def parse(self, text):
            self.calls += 1
            if self.calls == 2:
                raise ParserError('Unavailable test model')
            wrong = expected.model_copy(deep=True)
            wrong.hard_constraints[0].operator = '>='
            return wrong

    report = measure(gold, PartlyBrokenParser())
    assert report['queries'] == 2 and report['covered'] == 1
    assert report['exact_match'] == 0
    assert report['dimensions']['operators'] == {'correct': 0, 'expected': 2, 'predicted': 1}
    assert report['field_precision'] == .75  # 3 верных из 4 выданных полей.
    assert report['field_recall'] == .375  # 3 верных из 8 нужных полей, включая сбой.
    assert len(report['errors']) == 1 and len(report['mismatches']) == 2


def test_negation_is_not_counted_as_numeric_zero():
    query = FixtureQueryParser().parse('Нужен номер без вида на море').model_dump(mode='json')
    assert not dimension(query, 'numbers')
    assert dimension(query, 'negations')[('sea_view', False)] == 1
