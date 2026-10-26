"""Streamlit UI: подбор, объяснения, сравнение и подтверждение ответов отельера."""
import streamlit as st
import streamlit.components.v1 as components
from frontend.api_client import APIClient
from frontend.map_view import MapEngine, get_routes, offline_map
from frontend.environment_view import render_environment

st.set_page_config(page_title='О!дин шаг · Адлер',page_icon='🏖',layout='wide')
api = APIClient()
st.caption('О!ХАКАТОН  /  ПРИБРЕЖНЫЙ АДЛЕР')
st.title('На шаг ближе к своему отелю')
st.write('Расскажите, что важно. Мы покажем подходящие варианты и основания для выбора.')


def call(function,*args):
    try:
        return function(*args)
    except RuntimeError as exc:
        st.error(str(exc))
        return None


health = call(api.get,'/api/health')
if not health:
    st.stop()
if health['status']!='ok':
    st.error('Демо ещё не загружено: выполните python -m scripts.seed_demo')
    st.stop()
definitions = call(api.get,'/api/features') or {}
examples = call(api.get,'/api/demo-queries') or []
hotels = call(api.get,'/api/hotels') or []
names = {h['id']:h['name'] for h in hotels}
st.caption(f'{health["hotels"]} отелей из OSM · parser: {health["parser_mode"]} · цены и бронирование не подключены')
search_tab,owner_tab,environment_tab = st.tabs(['Найти свой отель','Отельер · демо','Среда вокруг отеля'])

with environment_tab:
    render_environment(api, hotels, call)


def show_result(result,index):
    h=result['hotel']
    with st.container(border=True):
        st.subheader(f'{index}. {h["name"]}')
        st.caption(f'Основание: OSM · {h["id"]}')
        if result['recommended_room_id']:
            st.write('Номер: '+result['recommended_room_id'].split(':room:')[-1])
        columns=st.columns(2)
        columns[0].metric('Оценка известных пожеланий','—' if result['score'] is None else f'{result["score"]:.2f} / 1')
        columns[1].metric('Покрытие пожеланий',f'{result["coverage"]:.0%}')
        if result.get('ranking_interval') is not None:
            lower,upper=result['ranking_interval']
            st.caption(f'Сортировочная оценка: {result["ranking_score"]:.2f}. Диапазон из-за неизвестных данных: {lower:.2f}–{upper:.2f}; это не вероятность.')
            if result.get('pareto_dominated'):
                st.caption('Есть другой вариант не хуже по всем известным пожеланиям и лучше хотя бы по одному.')
            with st.expander('Оценки по группам пожеланий'):
                for group in result.get('group_scores',[]):
                    st.write(f'{group["label"]}: {group["lower"]:.2f}–{group["upper"]:.2f}; покрытие {group["coverage"]:.0%}')
        for c in result['criteria']:
            label=definitions[c['feature_key']]['label']
            if c['actual'] is None:
                value='Нужно уточнить'
            elif isinstance(c['actual'],bool):
                value='Да' if c['actual'] else 'Нет'
            elif definitions[c['feature_key']]['unit']=='m':
                value=f'≈ {round(c["actual"]/10)*10:.0f} м'
            elif definitions[c['feature_key']]['unit']=='floor':
                value=f'с {c["actual"]:g}-го этажа'
            else:
                value=definitions[c['feature_key']].get('choice_labels',{}).get(c['actual'],str(c['actual']))
            st.write(f'**{label}: {value}**')
            st.caption(c['explanation'])
            for conflict in c.get('model_conflicts',[]):
                st.warning('Расхождение источников: '+conflict['text'])
        for warning in result['warnings']:
            st.warning(warning)
        with st.expander('Источники, даты и уверенность'):
            for c in result['criteria']:
                for observation in c['evidence']:
                    evidence=observation['evidence']
                    st.write(f'**{definitions[c["feature_key"]]["label"]}** · {observation["status"]} · уверенность: {observation["confidence_level"]}')
                    st.caption(f'{evidence["source"]["name"]} · получено {observation["collected_at"]} · метод {evidence["method"]}')
                    if evidence['source'].get('url'):
                        st.link_button('Проверить объект в OSM',evidence['source']['url'])
                    st.write(observation['confidence_method'])
                    st.json(observation,expanded=False)
        if result['pending_hotelier_question_ids']:
            st.info('Вопрос отельеру создан. Ответьте во вкладке «Отельер · демо».')
        st.link_button('Карточка объекта OSM',h['source_url'])


with search_tab:
    ranking_method=st.selectbox('Способ ранжирования',['balanced_v2','weighted_v1'],
        format_func=lambda value:'Баланс потребностей · v2' if value=='balanced_v2' else 'Взвешенная сумма · v1')
    if health['parser_mode']=='groq':
        st.caption('Облачная модель Groq: текст запроса отправляется провайдеру. Действуют квоты вашего аккаунта.')
    if health['parser_mode']=='fixture':
        st.info(f'Без модели доступны {len(examples)} проверенных формулировок. Для произвольного текста включите Ollama; незнакомый запрос потребует уточнения.')
    if health['parser_mode']=='offline':
        st.info('Пишите своими словами: без LLM запрос разбирается по правилам и словарю характеристик. '
                'Понимает тишину, пляж и расстояния, вид на море и закат, бары, самолёты, шумоизоляцию; '
                'неподдерживаемое (цена, бассейн, даты) попросит убрать.')
    example=st.selectbox('Попробовать сценарий',examples)
    text=st.text_area('Что важно в поездке?',value=example,key=f'query_{examples.index(example)}',height=95)
    simulated=st.checkbox('Учитывать симулированные ответы отельера',value=False,
                          help='Только демонстрация: эти ответы не описывают реальные свойства отелей.')
    if st.button('Найти отели',type='primary',use_container_width=True):
        response=call(api.post,'/api/search',{'text':text,'include_simulated':simulated,'ranking_method':ranking_method})
        if response:
            st.session_state['response']=response
            st.session_state['weight_signature']=None
            for pref in response['parsed']['soft_preferences']:
                st.session_state['weight_'+pref['feature_key']]=float(pref['importance'])
    response=st.session_state.get('response')
    if response:
        if response['status']=='needs_clarification':
            st.warning(response['parsed']['clarification_question'] or 'Уточните запрос: поддерживается прибрежный Адлер.')
            st.write(response['parsed']['unknown_or_ambiguous'])
        else:
            weights={}
            if response['parsed']['soft_preferences']:
                st.write('**Что важнее для вас?**')
                columns=st.columns(len(response['parsed']['soft_preferences']))
                for column,pref in zip(columns,response['parsed']['soft_preferences']):
                    key=pref['feature_key']
                    weights[key]=column.slider(definitions[key]['label'],0.,1.,float(pref['importance']),.1,key='weight_'+key)
                    if pref.get('derived_from'):
                        column.caption('Расчёт по геоданным к пожеланию «'+definitions[pref['derived_from']]['label'].lower()+'»')
            signature=(tuple(sorted(weights.items())),simulated,ranking_method)
            if signature!=st.session_state.get('weight_signature'):
                updated=call(api.post,'/api/search',{'parsed':response['parsed'],'weights':weights,'include_simulated':simulated,'ranking_method':ranking_method})
                if updated:
                    response=updated
                    st.session_state['response']=updated
                    st.session_state['weight_signature']=signature
            st.caption('Оценка — соответствие известным мягким пожеланиям; это не вероятность и не рейтинг гостиницы. Порядок учитывает покрытие данных.')
            with st.expander('Распознанный запрос и решения агента'):
                st.json(response['parsed'])
                st.json(response['trace'],expanded=False)
            selected=response['matched']+response['needs_verification']
            st.subheader('Отели и пути к пляжу')
            st.html(offline_map(selected))
            st.caption('Локальная схема работает без интернета. Номера точек соответствуют порядку карточек; наведите курсор для названия.')
            if st.checkbox('Показать онлайн-карту с подложкой (нужен интернет)') and selected:
                map_engine=MapEngine([43.432,39.921])
                map_engine.add_hotels([r['hotel'] for r in selected])
                map_engine.add_routes(get_routes(selected))
                components.html(map_engine.render(),height=470)
            st.subheader(f'Соответствуют по имеющимся данным · {len(response["matched"])}')
            if not response['matched']:
                st.write('Подтверждённого соответствия нет. Посмотрите варианты, требующие уточнения, или измените условия.')
            for index,result in enumerate(response['matched'],1):
                show_result(result,index)
            st.subheader(f'Нужно уточнить · {len(response["needs_verification"])}')
            for index,result in enumerate(response['needs_verification'],len(response['matched'])+1):
                show_result(result,index)
            with st.expander(f'Не прошли строгие условия · {len(response["excluded"])}'):
                for item in response['excluded']:
                    st.write(item['hotel']['name']+': '+'; '.join(c['explanation'] for c in item['criteria'] if c['outcome']=='violated'))
            compare=st.multiselect('Сравнить до трёх отелей',[r['hotel']['id'] for r in selected],format_func=lambda k:names[k],max_selections=3)
            if compare:
                columns=st.columns(len(compare))
                for col,hotel_id in zip(columns,compare):
                    row=next(r for r in selected if r['hotel']['id']==hotel_id)
                    col.write('**'+row['hotel']['name']+'**')
                    for criterion in row['criteria']:
                        col.write(definitions[criterion['feature_key']]['label'])
                        col.write(str(criterion['actual']) if criterion['actual'] is not None else 'Неизвестно')

with owner_tab:
    st.warning('Симулятор: вы подтверждаете корректность разбора учебного ответа. Это не подтверждение реального свойства гостиницы.')
    hotel_id=st.selectbox('Отель',list(names),format_func=lambda k:names[k])
    cabinet=call(api.get,f'/api/hotelier/hotels/{hotel_id}/facts') or {'facts':[],'conflicts':[]}
    st.subheader('Что система узнала о вашем отеле')
    st.caption('Подтвердите или исправьте. Исправление не перезаписывает расчёт: если версии расходятся, решает оператор.')
    for fact in cabinet['facts']:
        value='нужно уточнить' if fact['value'] is None else (
            f'≈ {round(fact["value"]/10)*10:.0f} м' if fact['unit']=='m' else fact['display'])
        mark=' · ✔ проверено отельером' if fact['reviewed_by_hotelier'] else ''
        with st.expander(f'{fact["label"]}: {value} · уверенность {fact["confidence_level"]}{mark}'):
            st.caption(fact['explanation'])
            with st.form(f'review_{fact["feature_key"]}'):
                key=fact['feature_key']
                verdict={'Верно':'confirm','Исправить':'correct'}[st.radio('Ваш ответ',['Верно','Исправить'],horizontal=True,
                                                                          key='verdict_'+key)]
                if fact['type']=='category':
                    labels=definitions[fact['feature_key']].get('choice_labels',{})
                    shown={labels.get(c,c):c for c in fact['choices']}
                    new_value=shown[st.selectbox('Правильное значение',list(shown),key='value_'+key)]
                elif fact['type']=='number':
                    new_value=st.number_input('Правильное значение',min_value=0.,value=float(fact['value'] or 0))
                else:
                    new_value=st.checkbox('Да',value=bool(fact['value']))
                comment=st.text_input('Комментарий (например, «перед отелем высокие деревья»)',key='comment_'+key)
                if st.form_submit_button('Отправить',key='submit_'+key):
                    payload={'hotel_id':hotel_id,'feature_key':fact['feature_key'],'verdict':verdict,'comment':comment}
                    if verdict=='correct':
                        payload['value']=new_value
                    result=call(api.post,'/api/hotelier/facts/review',payload)
                    if result:
                        st.success('Сохранено.' + (' Есть расхождение с расчётом — оно передано оператору.' if result['conflicts'] else ''))
                        st.rerun()
    open_conflicts=[c for c in cabinet['conflicts'] if not c.get('resolution')]
    if cabinet['conflicts']:
        st.subheader(f'Конфликты источников · открыто {len(open_conflicts)}')
        evidence=call(api.get,f'/api/hotels/{hotel_id}/evidence') or {'observations':[]}
        by_id={o['id']:o for o in evidence['observations']}
        for conflict in cabinet['conflicts']:
            label=definitions[conflict['feature_key']]['label']
            subject=conflict['subject_id'].split(':room:')[-1] if ':room:' in conflict['subject_id'] else 'отель'
            with st.expander(f'{label} · {subject} · {conflict["policy"]}' + (' · решён' if conflict.get('resolution') else '')):
                versions=[by_id[i] for i in (conflict['left_id'],conflict['right_id']) if i in by_id]
                describe=lambda o:(f'{o["evidence"]["source"]["name"]}: {o["value"]} · {o["evidence"]["method"]} · '
                                   f'{o["collected_at"][:10]}')
                for o in versions:
                    st.write('• '+describe(o))
                    st.caption(o['evidence']['details'].get('explanation') or o['evidence'].get('raw_excerpt') or '')
                if conflict.get('resolution'):
                    st.success(f'Решение: {conflict["resolution"]["value"]} — {conflict["resolution"]["reason"]}')
                elif versions:
                    with st.form(f'resolve_{conflict["id"]}'):
                        shown={describe(o):o['id'] for o in versions}
                        chosen=shown[st.radio('Какая версия верна',list(shown))]
                        reason=st.text_input('Причина решения')
                        if st.form_submit_button('Разрешить конфликт'):
                            if call(api.post,f'/api/hotelier/conflicts/{conflict["id"]}/resolve',
                                    {'chosen_observation_id':chosen,'reason':reason}):
                                st.rerun()
    st.subheader('Вопросы агента о номерах')
    keys=[k for k,d in definitions.items() if d['provider']=='hotelier']
    feature_key=st.selectbox('О чём спросить',keys,format_func=lambda k:definitions[k]['label'])
    if st.button('Сформировать вопрос'):
        call(api.post,'/api/hotelier/questions',{'hotel_id':hotel_id,'feature_key':feature_key})
    questions=call(api.get,'/api/hotelier/questions') or []
    if questions:
        qid=st.selectbox('Вопросы агента',[q['id'] for q in questions],format_func=lambda k:next(names[q['hotel_id']]+' · '+definitions[q['feature_key']]['label'] for q in questions if q['id']==k))
        question=next(q for q in questions if q['id']==qid)
        st.write(question['text'])
        reply=st.text_area('Ответ своими словами',placeholder='В номерах 301–305 вид на море, все на 3-м этаже.')
        if st.button('Разобрать ответ'):
            answer=call(api.post,f'/api/hotelier/questions/{qid}/answer',{'text':reply})
            if answer:
                st.session_state['pending_answer']=answer
        answer=st.session_state.get('pending_answer')
        if answer:
            st.write('**Проверьте извлечённые номера и значения**')
            st.json(answer['extraction'])
            if answer['extraction']['unparsed']:
                st.error('Есть неразобранный текст. Отклоните ответ и переформулируйте.')
            yes,no=st.columns(2)
            accepted=yes.button('Подтвердить разбор',disabled=bool(answer['extraction']['unparsed']) or not answer['extraction']['claims'])
            rejected=no.button('Отклонить')
            if accepted or rejected:
                result=call(api.post,f'/api/hotelier/answers/{answer["id"]}/confirm',{'accept':accepted})
                if result:
                    st.success('Решение сохранено. Повторите поиск с включённой симуляцией.')
                    st.json(result,expanded=False)
                    del st.session_state['pending_answer']
                    st.session_state['weight_signature']=None
    with st.expander('История свидетельств выбранного отеля'):
        if st.button('Загрузить историю'):
            st.json(call(api.get,f'/api/hotels/{hotel_id}/evidence'),expanded=False)

st.caption('Данные: © OpenStreetMap contributors · ODbL. Расчёты оценочные; наличие отеля в OSM не подтверждает текущую работу или доступность номеров.')
st.link_button('Лицензия и участники OSM','https://www.openstreetmap.org/copyright')
