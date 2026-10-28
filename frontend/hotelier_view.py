"""Элементы кабинета работают только через существующий HTTP-клиент."""
import streamlit as st
from frontend.conflict_client import ConflictClient

REASONS = {'unknown': 'не хватает сведений', 'stale': 'истёк срок действия сведений',
           'conflicted': 'есть противоречащие ответы', 'pending_answer': 'разбор ожидает проверки',
           'unparsed_answer': 'часть текста требует уточнения', 'rejected_answer': 'разбор отклонён'}


def render_question_state(question):
    if question['status'] == 'answered':
        st.success('Уточнение закрыто.')
        return
    context = question.get('context', {})
    reasons = context.get('reasons', [])
    if any(reason in ('stale', 'conflicted') for reason in reasons):
        st.warning('Вопрос снова требует уточнения.')
    else:
        st.info('Вопрос открыт.')
    if reasons:
        st.caption('Причины: ' + '; '.join(REASONS.get(reason, reason) for reason in reasons) + '.')
    if context.get('subject_ids'):
        st.caption('Нужно уточнить номера: ' + ', '.join(s.split(':room:')[-1] for s in context['subject_ids']))


def finish_owner_action(api, hotel_id, result):
    """Решение уже сохранено. Ошибка обновления не выдаётся за откат решения."""
    warnings = []
    previous = st.session_state.get('response')
    search_refreshed = False
    if previous and previous.get('status') == 'ok':
        st.session_state.pop('response', None)
        st.session_state['weight_signature'] = None
        payload = {'parsed': previous['parsed'],
                   'weights': {p['feature_key']: p['importance'] for p in previous['parsed']['soft_preferences']},
                   'include_simulated': previous['include_simulated'],
                   'ranking_method': previous['ranking_method'], 'balance': previous.get('balance', .25)}
        try:
            st.session_state['response'] = api.post('/api/search', payload)
            st.session_state['weight_signature'] = (tuple(sorted(payload['weights'].items())),
                payload['include_simulated'], payload['ranking_method'], payload['balance'])
            search_refreshed = True
        except RuntimeError as exc:
            warnings.append('Не удалось обновить подбор. Повторите поиск. ' + str(exc))
    cache = dict(st.session_state.get('owner_evidence', {}))
    cache.pop(hotel_id, None)
    try:
        cache[hotel_id] = api.get(f'/api/hotels/{hotel_id}/evidence')
    except RuntimeError as exc:
        warnings.append('Не удалось перечитать историю. ' + str(exc))
    st.session_state['owner_evidence'] = cache
    current = result.get('current')
    if current is not None and current.get('value') is None:
        warnings.append('Решение по этой паре сохранено, но свойство всё ещё требует проверки: '
                        + REASONS.get(current['status'], current['status']) + '.')
    st.session_state['owner_feedback'] = {'hotel_id': hotel_id, 'result': result,
                                         'warnings': warnings, 'search_refreshed': search_refreshed}
    st.rerun()


def render_owner_feedback(hotel_id):
    feedback = st.session_state.get('owner_feedback')
    if feedback is None or feedback['hotel_id'] != hotel_id:
        return
    message = 'Решение сохранено.'
    if feedback['search_refreshed']:
        message += ' Подбор обновлён с прежними условиями.'
    st.success(message)
    for warning in feedback['warnings']:
        st.warning(warning)
    with st.expander('Результат сохранения'):
        st.json(feedback['result'], expanded=False)


def display_value(observation, definitions):
    value = observation['value']
    if value is None:
        return 'Неизвестно'
    if isinstance(value, bool):
        return 'Да' if value else 'Нет'
    unit = definitions.get(observation['feature_key'], {}).get('unit')
    return str(value) + (' ' + unit if unit else '')


def render_conflicts(api, hotel_id, hotel_name, definitions, call):
    st.subheader('Противоречия · ' + hotel_name)
    client = ConflictClient(api)
    conflicts = call(client.list_conflicts, hotel_id, 'open')
    if conflicts is None:
        return
    if not conflicts:
        st.info('Неразрешённых противоречий нет.')
        return
    lookup = {c['id']: c for c in conflicts}
    def title(cid):
        c = lookup[cid]
        label = definitions.get(c['feature_key'], {}).get('label', c['feature_key'])
        return label + ' · ' + c['subject_id'].split(':room:')[-1]
    cid = st.selectbox('Какое противоречие разобрать?', list(lookup), format_func=title,
                      key='owner_conflict_' + hotel_id)
    conflict = lookup[cid]
    versions = [conflict['left_observation'], conflict['right_observation']]
    for index, (column, observation) in enumerate(zip(st.columns(2), versions), 1):
        with column:
            st.write(f'**Версия {index}: {display_value(observation, definitions)}**')
            evidence = observation['evidence']
            st.caption('Источник: ' + evidence['source']['name'])
            st.caption('Получено: ' + observation['collected_at'])
            st.caption('Действует до: ' + observation['expires_at'])
            confidence = {'low': 'низкая', 'medium': 'средняя', 'high': 'высокая', 'unknown': 'неизвестна'}
            st.caption('Достоверность: ' + confidence.get(observation['confidence_level'], observation['confidence_level']))
            quote = evidence.get('details', {}).get('quote') or evidence.get('raw_excerpt')
            if quote:
                st.write('Цитата: ' + quote)
    ids = [o['id'] for o in versions]
    selected = st.radio('Какую версию сохранить?', ids, index=None,
                        format_func=lambda oid: 'Версия ' + str(ids.index(oid) + 1) + ': '
                        + display_value(versions[ids.index(oid)], definitions), key='owner_choice_' + cid)
    reason = st.text_area('Почему выбрана эта версия?', max_chars=2000, key='owner_reason_' + cid)
    if st.button('Сохранить решение', disabled=selected is None or not reason.strip(), key='owner_resolve_' + cid):
        result = call(client.resolve_conflict, cid, selected, reason.strip())
        if result:
            finish_owner_action(api, hotel_id, result)
