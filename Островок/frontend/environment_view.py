"""Экран источников среды: станция, даты, покрытие и ограничения акустики."""
import streamlit as st


STATUS = {'not_collected':'Данные ещё не запрошены', 'not_configured':'OpenAQ не подключён',
          'no_stations':'В радиусе поиска нет подходящих стационарных датчиков PM2.5',
          'no_suitable_station':'Нет станции с достаточной полнотой и свежестью данных',
          'provider_error':'Не удалось получить данные источника', 'available':'Есть пригодные измерения',
          'needs_data':'Для акустического расчёта не хватает данных',
          'ready':'Входы подготовлены', 'ready_scenario':'Подготовлен учебный сценарий',
          'scenario':'Учебный акустический сценарий', 'modeled':'Расчёт внешнего дорожного шума'}


def render_environment(api, hotels, call):
    st.write('**Воздух и шум вокруг отеля**')
    st.caption('Измерения станций и расчётные сценарии показаны отдельно. В подбор и ранжирование они пока не входят.')
    if not hotels:
        return
    names = {h['id']: h['name'] for h in hotels}
    hotel_id = st.selectbox('Отель для проверки среды', list(names), format_func=lambda key:names[key])
    if st.button('Обновить данные OpenAQ'):
        with st.spinner('Проверяем станции и полноту измерений за последние 7 суток…'):
            call(api.post, f'/api/hotels/{hotel_id}/environment/air-quality/refresh', {})
    reports = call(api.get, f'/api/hotels/{hotel_id}/environment')
    if not reports:
        return
    for kind, title in (('air_quality','Качество воздуха'), ('noise','Шум у фасадов')):
        report = reports[kind]
        st.subheader(title)
        st.write(STATUS.get(report['status'], report['status']))
        if report.get('cache_stale'):
            st.warning('Сохранённый отчёт устарел; обновите данные перед использованием.')
        if report.get('collected_at'):
            st.caption('Отчёт получен: ' + report['collected_at'])
        if kind == 'air_quality':
            st.info('Это измерение станции поблизости, не непосредственно у окна гостиницы.')
            if report.get('reason'):
                st.caption(report['reason'])
            selected = report.get('selected')
            if selected:
                st.metric('PM2.5 · среднее по пригодным часам', f'{selected["mean_pm25"]} {selected["unit"]}')
                st.write(f'Станция: {selected["station_name"]} · ID {selected["station_id"]} · датчик {selected["sensor_id"]}')
                st.write(f'Расстояние: {selected["distance_m"]/1000:.1f} км · полнота: {selected["coverage_fraction"]:.0%}')
                st.caption(f'Период: {report["period_from"]} — {report["period_to"]}; последнее измерение: {selected["latest_measurement_at"]}')
                st.link_button('Проверить станцию в OpenAQ', selected['source_url'])
        else:
            if report.get('scenario'):
                st.warning('Условные интенсивности движения и часть высот. Эти числа НЕ описывают реальный шум в отеле.')
            receivers = report.get('receivers', [])
            if receivers:
                st.caption(f'Расчётных точек у фасадов: {len(receivers)}. Это не подтверждённые окна номеров.')
            if report.get('levels'):
                for period, label in [('D','День'), ('E','Вечер'), ('N','Ночь')]:
                    values = [v['laeq_db'] for v in report['levels'] if v['period'] == period]
                    if values:
                        st.write(f'{label}: {min(values):.1f}–{max(values):.1f} дБ(A) по расчётным точкам')
            st.caption('Аэропорт, железная дорога, бары и шум внутри номера в акустический расчёт пока не входят. Отсутствие расчёта не означает тишину.')
        with st.expander('Исходные сведения и ограничения · ' + title):
            st.json(report, expanded=False)
